"""Shared helpers for safe flat-orphan ledger reconciliation."""

from __future__ import annotations

import inspect
import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import select

from src.services.persistence_service import OrderStatus, TradeLedger, persistence_service

logger = logging.getLogger(__name__)

FLAT_RECONCILE_STATUSES = (
    OrderStatus.FAILED,
    OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
    OrderStatus.NEEDS_MANUAL_RECONCILIATION,
)


def normalize_symbol(symbol: str) -> str:
    return str(symbol or "").upper().replace("/", "-").replace("_", "-")


def symbols_match(left: str, right: str) -> bool:
    left_norm = normalize_symbol(left)
    right_norm = normalize_symbol(right)
    return left_norm == right_norm or left_norm.replace("-", "") == right_norm.replace("-", "")


def position_quantity(position: dict) -> float:
    value = (
        position.get("quantityAvailableForTrading")
        or position.get("availableQuantity")
        or position.get("tradableQuantity")
        or position.get("quantity")
        or position.get("qty")
        or 0.0
    )
    return float(value or 0.0)


def matching_orders(row: TradeLedger, pending_orders: list[dict]) -> list[dict]:
    row_order_id = str(row.order_id or "")
    matches: list[dict] = []
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
        if symbols_match(order.get("ticker") or order.get("symbol"), row.ticker):
            matches.append(order)
    return matches


def is_flat_orphan_candidate(row: TradeLedger) -> bool:
    status = row.status
    status_value = status.value if isinstance(status, OrderStatus) else str(status)
    order_id = str(row.order_id or "")
    if order_id.startswith("ORPHAN_"):
        return True
    meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    if meta.get("orphaned") is True:
        return True
    return status in FLAT_RECONCILE_STATUSES or status_value in {
        s.value for s in FLAT_RECONCILE_STATUSES
    }


def broker_qty_for_ticker(positions: Iterable[dict], ticker: str) -> float:
    for position in positions:
        if symbols_match(position.get("ticker") or position.get("symbol"), ticker):
            return abs(position_quantity(position))
    return 0.0


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def auto_close_flat_orphans(
    *,
    brokerage,
    dry_run: bool = False,
) -> dict:
    """Close FAILED/ORPHAN rows only when broker is flat for that ticker.

    Returns summary counts. Fail-closed: if broker state cannot be read, closes nothing.
    """
    async with persistence_service.AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(TradeLedger)
                .where(TradeLedger.status.in_(persistence_service._startup_unresolved_statuses()))
                .where(TradeLedger.closed_at.is_(None))
            )
        ).scalars().all()

        if not rows:
            return {"examined": 0, "closed": 0, "blocked": 0, "broker_ok": True}

        try:
            positions = await _maybe_await(brokerage.get_portfolio())
            pending_orders = await _maybe_await(brokerage.get_pending_orders())
            broker_ok = True
        except Exception as exc:
            logger.error("Auto-reconcile aborted: broker state unreadble: %s", exc)
            return {
                "examined": len(rows),
                "closed": 0,
                "blocked": len(rows),
                "broker_ok": False,
                "error": str(exc),
            }

        closed = 0
        blocked = 0
        now = datetime.now(timezone.utc)
        for row in rows:
            if not is_flat_orphan_candidate(row):
                blocked += 1
                continue
            broker_qty = broker_qty_for_ticker(positions or [], row.ticker)
            open_orders = matching_orders(row, pending_orders or [])
            if abs(broker_qty) > 1e-9 or open_orders:
                blocked += 1
                logger.info(
                    "Auto-reconcile skip ledger_id=%s ticker=%s broker_qty=%s open_orders=%s",
                    row.id,
                    row.ticker,
                    broker_qty,
                    [o.get("id") or o.get("order_id") for o in open_orders],
                )
                continue
            if dry_run:
                closed += 1
                continue
            meta = dict(row.metadata_json or {})
            meta["auto_reconciliation"] = {
                "broker_qty": broker_qty,
                "open_order_ids": [o.get("id") or o.get("order_id") for o in open_orders],
                "reconciled_at": now.isoformat(),
                "method": "auto_close_flat_orphans",
            }
            row.status = OrderStatus.CLOSED
            row.closed_at = now
            row.metadata_json = meta
            session.add(row)
            closed += 1
            logger.info("Auto-reconcile CLOSED ledger_id=%s ticker=%s", row.id, row.ticker)

        if not dry_run and closed:
            await session.commit()

        return {
            "examined": len(rows),
            "closed": closed,
            "blocked": blocked,
            "broker_ok": broker_ok,
        }
