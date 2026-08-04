from typing import Dict, List, Optional, Tuple
import logging
from src.services.persistence_service import persistence_service, OrderSide, OrderStatus
from src.config import settings
import uuid

logger = logging.getLogger(__name__)


def apply_shadow_fill_slippage(
    mid_price: float,
    side: str,
    *,
    slippage_bps: Optional[float] = None,
) -> Tuple[float, float]:
    """Push shadow fills adversely away from mid.

    BUY pays up; SELL receives less. Returns ``(fill_price, slippage_bps_applied)``.
    """
    bps = float(
        settings.SHADOW_FILL_SLIPPAGE_BPS if slippage_bps is None else slippage_bps
    )
    bps = max(0.0, bps)
    mid = float(mid_price)
    if mid <= 0.0 or bps <= 0.0:
        return mid, 0.0
    fraction = bps / 10_000.0
    side_u = str(side).upper()
    if side_u in ("BUY", "LONG"):
        return mid * (1.0 + fraction), bps
    return mid * (1.0 - fraction), bps


class ShadowService:
    def __init__(self):
        self._sector_map: dict = {}
        for pair_key, sector in settings.PAIR_SECTORS.items():
            for ticker in pair_key.split("_"):
                self._sector_map[ticker] = sector

    async def execute_simulated_trade(self, pair_id, direction, size_a, size_b, price_a, price_b, signal_id=None):
        t_a, t_b = pair_id.split("_")
        trade_id_a = str(uuid.uuid4())
        trade_id_b = str(uuid.uuid4())
        if signal_id is None:
            signal_id = uuid.uuid4()
        elif isinstance(signal_id, str):
            signal_id = uuid.UUID(signal_id)

        side_a = OrderSide.SELL if direction == "Short-Long" else OrderSide.BUY
        side_b = OrderSide.BUY if direction == "Short-Long" else OrderSide.SELL
        fill_a, slip_a = apply_shadow_fill_slippage(price_a, side_a.value)
        fill_b, slip_b = apply_shadow_fill_slippage(price_b, side_b.value)
        leg_fee = float(settings.FLAT_ORDER_FRICTION_USD)

        shadow_meta = {
            "is_shadow": True,
            "execution_lane": "SHADOW",
            "broker_paper_trading": False,
            "direction": direction,
            "mid_price_a": float(price_a),
            "mid_price_b": float(price_b),
            "shadow_slippage_bps": float(settings.SHADOW_FILL_SLIPPAGE_BPS),
            # Fill ``price`` already embeds adverse slip — do NOT also set
            # ``slippage_bps`` (that key is re-applied in calculate_realized_pnl).
        }
        # Single transaction: never leave a 1-leg OPEN shadow signal if leg B fails.
        await persistence_service.log_trades([
            {
                "order_id": trade_id_a, "signal_id": signal_id, "ticker": t_a,
                "side": side_a,
                "quantity": size_a, "price": fill_a, "fee": leg_fee,
                "status": OrderStatus.OPEN,
                "metadata_json": {
                    **shadow_meta,
                    "applied_slippage_bps": slip_a,
                    "theoretical_mid": float(price_a),
                },
            },
            {
                "order_id": trade_id_b, "signal_id": signal_id, "ticker": t_b,
                "side": side_b,
                "quantity": size_b, "price": fill_b, "fee": leg_fee,
                "status": OrderStatus.OPEN,
                "metadata_json": {
                    **shadow_meta,
                    "applied_slippage_bps": slip_b,
                    "theoretical_mid": float(price_b),
                },
            },
        ])
        logger.info(
            "SHADOW TRADE EXECUTED: %s for %s at fill %.4f/%.4f (mid %.4f/%.4f, slip %sbps)",
            direction, pair_id, fill_a, fill_b, price_a, price_b, settings.SHADOW_FILL_SLIPPAGE_BPS,
        )
        return signal_id

    def slip_exit_mids(
        self,
        direction: str,
        exit_price_a: float,
        exit_price_b: float,
    ) -> Tuple[float, float]:
        """Adverse-slip exit mids for a shadow close (BUY pays up / SELL receives less)."""
        if direction == "Short-Long":
            # Leg A was SELL / Leg B was BUY at open → close is BUY A / SELL B
            exit_a, _ = apply_shadow_fill_slippage(exit_price_a, "BUY")
            exit_b, _ = apply_shadow_fill_slippage(exit_price_b, "SELL")
        else:
            exit_a, _ = apply_shadow_fill_slippage(exit_price_a, "SELL")
            exit_b, _ = apply_shadow_fill_slippage(exit_price_b, "BUY")
        return exit_a, exit_b

    async def close_simulated_trade(self, pair_id, signal_id, direction, size_a, size_b, entry_price_a, entry_price_b, exit_price_a, exit_price_b):
        """
        Compute and log shadow PnL for a paper-trade close.
        Exit mids are slipped adversely before PnL so closes match open realism.
        DB persistence (close_trade) is intentionally left to the caller (_close_position)
        so exit_reason is preserved and there is a single write path for both live and paper.
        Caller should pass the same slipped exits into ``calculate_realized_pnl`` for the ledger.
        """
        exit_a, exit_b = self.slip_exit_mids(direction, exit_price_a, exit_price_b)
        if direction == "Short-Long":
            pnl_a = (entry_price_a - exit_a) * size_a
            pnl_b = (exit_b - entry_price_b) * size_b
        else:
            pnl_a = (exit_a - entry_price_a) * size_a
            pnl_b = (entry_price_b - exit_b) * size_b
        # Round-trip flat friction on both legs (open already booked; charge exit here).
        exit_fees = 2.0 * float(settings.FLAT_ORDER_FRICTION_USD)
        total_pnl = pnl_a + pnl_b - exit_fees
        logger.info(
            "SHADOW TRADE CLOSED: %s for %s — leg_a PnL=%.4f, leg_b PnL=%.4f, exit_fees=%.4f, total=%.4f",
            direction, pair_id, pnl_a, pnl_b, exit_fees, total_pnl,
        )
        return total_pnl, exit_a, exit_b

    async def get_active_portfolio_with_sectors(self):
        """Build sized holdings for sector cluster guards.

        Includes all open-ish ledger statuses (not only OPEN) so PARTIAL_EXPOSURE /
        OPEN_PAIR / CLOSING rows still count toward concentration. Sector labels
        use ``Unassigned`` (not legacy ``General``) so they match resolve_pair_sector.
        """
        from sqlalchemy import select
        from src.services.persistence_service import TradeLedger
        from src.services.portfolio_book_guards import normalize_sector_label

        open_statuses = (
            OrderStatus.OPEN,
            OrderStatus.OPEN_PAIR,
            OrderStatus.PARTIAL_EXPOSURE,
            OrderStatus.CLOSING,
        )
        async with persistence_service.AsyncSessionLocal() as session:
            stmt = select(TradeLedger).where(TradeLedger.status.in_(open_statuses))
            result = await session.execute(stmt)
            trades = result.scalars().all()
            portfolio = []
            for trade in trades:
                sector = normalize_sector_label(
                    self._sector_map.get(trade.ticker, "Unassigned")
                )
                portfolio.append({
                    "ticker": trade.ticker,
                    "size": float(trade.quantity * trade.price),
                    "sector": sector,
                })
            return portfolio


shadow_service = ShadowService()
