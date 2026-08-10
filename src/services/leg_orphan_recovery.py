"""Automatic Leg-A orphan recovery after crash mid-pair (R-302 / Phase-4).

Broker is the source of truth. Local ledger states LEG_A_* without a matching
Leg B are inspected against broker positions/orders; when Leg A exposure exists
and Leg B does not, the system places an emergency close automatically.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from src.services.ledger_reconcile_service import (
    broker_qty_for_ticker,
    matching_orders,
    normalize_symbol,
    _maybe_await,
)
from src.services.persistence_service import (
    OrderSide,
    OrderStatus,
    TradeLedger,
    persistence_service,
)

logger = logging.getLogger(__name__)

LEG_A_ORPHAN_STATUSES = (
    OrderStatus.ORDER_SUBMITTED,
    OrderStatus.LEG_A_SUBMITTED,
    OrderStatus.LEG_A_FILLED,
    OrderStatus.LEG_A_PARTIAL,
    OrderStatus.PARTIAL_EXPOSURE,
)


async def recover_leg_a_orphans(*, brokerage, dry_run: bool = False) -> dict[str, Any]:
    """Find one-legged exposures and flatten Leg A when Leg B never arrived."""
    async with persistence_service.AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(TradeLedger)
                .where(TradeLedger.status.in_(LEG_A_ORPHAN_STATUSES))
                .where(TradeLedger.closed_at.is_(None))
            )
        ).scalars().all()

    if not rows:
        return {"examined": 0, "recovered": 0, "skipped": 0, "broker_ok": True}

    try:
        positions = await _maybe_await(brokerage.get_portfolio())
        pending = await _maybe_await(brokerage.get_pending_orders())
    except Exception as exc:  # noqa: BLE001
        logger.error("leg_orphan_recovery: broker unreadble: %s", exc)
        return {
            "examined": len(rows),
            "recovered": 0,
            "skipped": len(rows),
            "broker_ok": False,
            "error": str(exc),
        }

    by_signal: dict[str, list[TradeLedger]] = {}
    for row in rows:
        sid = str(row.signal_id) if row.signal_id else ""
        by_signal.setdefault(sid or "__none__", []).append(row)

    recovered = 0
    skipped = 0
    actions: list[dict[str, Any]] = []

    for signal_id, legs in by_signal.items():
        tickers = {normalize_symbol(r.ticker) for r in legs}
        # True pair open has two distinct legs still unresolved — leave to pair restore.
        if len(tickers) >= 2:
            # Check whether both have broker qty — if only one does, orphan.
            with_qty = [
                t
                for t in tickers
                if abs(broker_qty_for_ticker(positions or [], t)) > 1e-9
            ]
            if len(with_qty) != 1:
                skipped += 1
                continue
            orphan_ticker = with_qty[0]
        else:
            orphan_ticker = next(iter(tickers)) if tickers else None
            if not orphan_ticker:
                skipped += 1
                continue
            if abs(broker_qty_for_ticker(positions or [], orphan_ticker)) <= 1e-9:
                # No broker exposure — flat orphan path handles ledger close.
                skipped += 1
                continue

        leg_row = next(
            (r for r in legs if normalize_symbol(r.ticker) == orphan_ticker),
            legs[0],
        )
        open_orders = matching_orders(leg_row, pending or [])
        if open_orders:
            skipped += 1
            actions.append(
                {
                    "signal_id": signal_id,
                    "action": "skip_pending_orders",
                    "ticker": orphan_ticker,
                }
            )
            continue

        qty = abs(float(leg_row.quantity or 0.0))
        broker_qty = abs(broker_qty_for_ticker(positions or [], orphan_ticker))
        close_qty = min(qty, broker_qty) if qty > 0 else broker_qty
        if close_qty <= 0:
            skipped += 1
            continue

        side = leg_row.side.value if isinstance(leg_row.side, OrderSide) else str(leg_row.side)
        close_side = "SELL" if str(side).upper() == "BUY" else "BUY"
        client_order_id = f"ORPHAN-CLOSE-{signal_id}-{orphan_ticker}"

        actions.append(
            {
                "signal_id": signal_id,
                "action": "emergency_close",
                "ticker": orphan_ticker,
                "qty": close_qty,
                "side": close_side,
                "dry_run": dry_run,
            }
        )
        if dry_run:
            recovered += 1
            continue

        try:
            place = getattr(brokerage, "place_market_order", None)
            if place is not None:
                result = await place(
                    orphan_ticker,
                    close_qty,
                    close_side,
                    client_order_id=client_order_id,
                    intent="close",
                )
            else:
                result = await brokerage.place_value_order(
                    orphan_ticker,
                    float(leg_row.price or 0) * close_qty,
                    close_side,
                    client_order_id=client_order_id,
                    intent="close",
                )
            status = str((result or {}).get("status") or "").lower()
            if status in {"error", "rejected"}:
                logger.critical(
                    "leg_orphan_recovery FAILED signal=%s ticker=%s result=%s",
                    signal_id,
                    orphan_ticker,
                    result,
                )
                skipped += 1
                continue

            # Alpaca "success" means submit accepted, not fill confirmed.
            # Only filled/closed may flatten the ledger; otherwise leave manual.
            fill_confirmed = status in {"filled", "closed"}
            if signal_id and signal_id != "__none__":
                await persistence_service.update_signal_status(
                    uuid.UUID(signal_id),
                    OrderStatus.CLOSED
                    if fill_confirmed
                    else OrderStatus.NEEDS_MANUAL_RECONCILIATION,
                )
            if fill_confirmed:
                async with persistence_service.AsyncSessionLocal() as session:
                    async with session.begin():
                        for row in legs:
                            if normalize_symbol(row.ticker) != orphan_ticker:
                                continue
                            row.status = OrderStatus.CLOSED
                            row.closed_at = datetime.now(timezone.utc)
                            meta = dict(row.metadata_json or {})
                            meta["orphan_recovered"] = True
                            meta["orphan_close_client_order_id"] = client_order_id
                            row.metadata_json = meta
                            session.add(row)
                recovered += 1
                logger.warning(
                    "leg_orphan_recovery: closed orphan Leg A signal=%s ticker=%s qty=%s",
                    signal_id,
                    orphan_ticker,
                    close_qty,
                )
            else:
                skipped += 1
                logger.critical(
                    "leg_orphan_recovery PENDING FILL signal=%s ticker=%s "
                    "status=%s — marked NEEDS_MANUAL_RECONCILIATION (no ledger flatten)",
                    signal_id,
                    orphan_ticker,
                    status,
                )
        except Exception as exc:  # noqa: BLE001
            logger.critical(
                "leg_orphan_recovery exception signal=%s: %s", signal_id, exc
            )
            skipped += 1

    return {
        "examined": len(by_signal),
        "recovered": recovered,
        "skipped": skipped,
        "broker_ok": True,
        "actions": actions,
    }
