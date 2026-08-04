from typing import Dict, List
import logging
from src.services.persistence_service import persistence_service, OrderSide, OrderStatus
from src.config import settings
import uuid

logger = logging.getLogger(__name__)


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
        shadow_meta = {
            "is_shadow": True,
            "execution_lane": "SHADOW",
            "broker_paper_trading": False,
            "direction": direction,
        }
        # Single transaction: never leave a 1-leg OPEN shadow signal if leg B fails.
        await persistence_service.log_trades([
            {
                "order_id": trade_id_a, "signal_id": signal_id, "ticker": t_a,
                "side": OrderSide.SELL if direction == "Short-Long" else OrderSide.BUY,
                "quantity": size_a, "price": price_a, "status": OrderStatus.OPEN,
                "metadata_json": dict(shadow_meta),
            },
            {
                "order_id": trade_id_b, "signal_id": signal_id, "ticker": t_b,
                "side": OrderSide.BUY if direction == "Short-Long" else OrderSide.SELL,
                "quantity": size_b, "price": price_b, "status": OrderStatus.OPEN,
                "metadata_json": dict(shadow_meta),
            },
        ])
        logger.info("SHADOW TRADE EXECUTED: %s for %s at %.4f/%.4f", direction, pair_id, price_a, price_b)
        return signal_id

    async def close_simulated_trade(self, pair_id, signal_id, direction, size_a, size_b, entry_price_a, entry_price_b, exit_price_a, exit_price_b):
        """
        Compute and log shadow PnL for a paper-trade close.
        DB persistence (close_trade) is intentionally left to the caller (_close_position)
        so exit_reason is preserved and there is a single write path for both live and paper.
        """
        if direction == "Short-Long":
            pnl_a = (entry_price_a - exit_price_a) * size_a
            pnl_b = (exit_price_b - entry_price_b) * size_b
        else:
            pnl_a = (exit_price_a - entry_price_a) * size_a
            pnl_b = (entry_price_b - exit_price_b) * size_b
        total_pnl = pnl_a + pnl_b
        logger.info("SHADOW TRADE CLOSED: %s for %s — leg_a PnL=%.4f, leg_b PnL=%.4f, total=%.4f",
                    direction, pair_id, pnl_a, pnl_b, total_pnl)
        return total_pnl

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
