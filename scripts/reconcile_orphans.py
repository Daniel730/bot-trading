import asyncio
import inspect
import logging
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from src.services.persistence_service import persistence_service, OrderStatus, TradeLedger
from src.services.brokerage_service import BrokerageService
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("reconcile_orphans")

def _enum_value(value):
    return getattr(value, "value", value)

def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").upper().replace("/", "-").replace("_", "-")

def _symbols_match(left: str, right: str) -> bool:
    left_norm = _normalize_symbol(left)
    right_norm = _normalize_symbol(right)
    return left_norm == right_norm or left_norm.replace("-", "") == right_norm.replace("-", "")

def _position_quantity(position: dict) -> float:
    value = (
        position.get("quantityAvailableForTrading")
        or position.get("availableQuantity")
        or position.get("tradableQuantity")
        or position.get("quantity")
        or position.get("qty")
        or 0.0
    )
    return float(value or 0.0)

def _matching_orders(row, pending_orders: list[dict]) -> list[dict]:
    row_order_id = str(row.order_id or "")
    matches = []
    for order in pending_orders:
        order_ids = {
            str(order.get("id") or ""),
            str(order.get("order_id") or ""),
            str(order.get("client_order_id") or ""),
            str(order.get("clientOrderId") or ""),
        }
        if row_order_id and row_order_id in order_ids:
            matches.append(order)
            continue
        if _symbols_match(order.get("ticker") or order.get("symbol"), row.ticker):
            matches.append(order)
    return matches

async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value

async def reconcile_orphans(dry_run: bool = True):
    """
    Reports orphan entries in the trade ledger that block startup.
    """
    logger.info(f"{'DRY RUN' if dry_run else 'LIVE RUN'}: Reporting orphan trades...")

    target_statuses = [
        OrderStatus.ORDER_SUBMITTED,
        OrderStatus.LEG_A_SUBMITTED,
        OrderStatus.LEG_A_PARTIAL,
        OrderStatus.LEG_B_SUBMITTED,
        OrderStatus.LEG_B_PARTIAL,
        OrderStatus.PARTIAL_EXPOSURE,
        OrderStatus.CLOSING,
        OrderStatus.CLOSE_FAILED,
        OrderStatus.NEEDS_MANUAL_RECONCILIATION,
        OrderStatus.FAILED,
        OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
    ]

    async with persistence_service.AsyncSessionLocal() as session:
        stmt_select = (
            select(TradeLedger)
            .where(TradeLedger.status.in_(target_statuses))
            .where(TradeLedger.closed_at.is_(None))
        )
        res_select = await session.execute(stmt_select)
        rows = res_select.scalars().all()

        if not rows:
            logger.info("No orphan entries found. Cleanup complete.")
            return 0

        logger.info(f"Found {len(rows)} entries requiring reconciliation.")

        brokerage = BrokerageService()
        try:
            positions = await _maybe_await(brokerage.get_portfolio())
            pending_orders = await _maybe_await(brokerage.get_pending_orders())
        except Exception as exc:
            positions = []
            pending_orders = []
            logger.error(
                "Broker state read failed; manual reconciliation remains blocked: %s",
                exc,
            )

        for row in rows:
            matching_position = next(
                (
                    position
                    for position in positions
                    if _symbols_match(
                        position.get("ticker") or position.get("symbol"),
                        row.ticker,
                    )
                ),
                None,
            )
            matching_orders = _matching_orders(row, pending_orders)
            broker_qty = _position_quantity(matching_position) if matching_position else 0.0
            logger.info(
                "  [REVIEW] ledger_id=%s signal_id=%s order_id=%s ticker=%s side=%s "
                "qty=%s status=%s venue=%s broker_qty=%s open_order_ids=%s",
                row.id,
                row.signal_id,
                row.order_id,
                row.ticker,
                _enum_value(row.side),
                row.quantity,
                _enum_value(row.status),
                row.venue,
                broker_qty,
                [order.get("id") or order.get("order_id") for order in matching_orders],
            )

        if not dry_run:
            logger.error(
                "--live is disabled: this script is read-only and will not close, "
                "reopen, or mark ledger rows reconciled. Resolve rows manually after "
                "comparing broker positions/open orders with the report above."
            )
            return 2

        logger.info("Dry run complete. No ledger rows were changed.")
        return 0

if __name__ == "__main__":
    is_live = "--live" in sys.argv
    sys.exit(asyncio.run(reconcile_orphans(dry_run=not is_live)))
