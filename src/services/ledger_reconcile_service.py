"""Shared helpers for safe flat-orphan ledger reconciliation."""

from __future__ import annotations

import inspect
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional

from sqlalchemy import select

from src.services.persistence_service import OrderStatus, TradeLedger, persistence_service

try:
    from src.services.trade_math import is_broker_fill_complete
except ImportError:  # pragma: no cover - older deployed images
    def is_broker_fill_complete(
        *,
        status: str,
        filled_qty: float,
        expected_qty: float = 0.0,
        fill_price: float = 0.0,
        expected_notional: float = 0.0,
        qty_tolerance: float = 0.05,
        notional_tolerance: float = 0.05,
    ) -> bool:
        status_norm = str(status or "").lower()
        filled = float(filled_qty or 0.0)
        if filled <= 0 or status_norm in ("partially_filled", "partial_fill"):
            return False
        if status_norm != "filled":
            return False
        expected = float(expected_qty or 0.0)
        if expected > 0 and filled + 1e-12 >= expected * max(0.0, 1.0 - qty_tolerance):
            return True
        notion_expected = float(expected_notional or 0.0)
        price = float(fill_price or 0.0)
        if notion_expected > 0 and price > 0:
            if filled * price + 1e-9 >= notion_expected * max(0.0, 1.0 - notional_tolerance):
                return True
        if expected > 0 or notion_expected > 0:
            return False
        return True

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


class SignalReconciliationAction(str, Enum):
    SAFE_AUTO_CLOSE = "safe_auto_close"
    SAFE_AUTO_RESTORE_OPEN = "safe_auto_restore_open"
    MANUAL_REQUIRED = "manual_required"


@dataclass
class LegReconciliationPlan:
    ledger_id: str
    order_id: str | None
    ticker: str
    side: str
    quantity: float
    price: float
    status: str
    broker_qty_signed: float
    broker_qty_abs: float
    open_order_ids: list[str] = field(default_factory=list)
    order_snapshot: dict | None = None
    order_snapshot_error: str | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass
class SignalReconciliationPlan:
    signal_id: str
    action: SignalReconciliationAction
    legs: list[LegReconciliationPlan]
    reasons: list[str] = field(default_factory=list)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def signed_broker_qty_for_ticker(positions: Iterable[dict], ticker: str) -> float:
    for position in positions:
        if symbols_match(position.get("ticker") or position.get("symbol"), ticker):
            return position_quantity(position)
    return 0.0


def _order_snapshot_ids(order: dict) -> set[str]:
    return {
        str(order.get("id") or ""),
        str(order.get("order_id") or ""),
        str(order.get("client_order_id") or ""),
        str(order.get("clientOrderId") or ""),
    }


def _pending_orders_for_row(row: TradeLedger, pending_orders: list[dict]) -> list[dict]:
    row_order_id = str(row.order_id or "")
    matches: list[dict] = []
    for order in pending_orders:
        if row_order_id and row_order_id in _order_snapshot_ids(order):
            matches.append(order)
            continue
        if symbols_match(order.get("ticker") or order.get("symbol"), row.ticker):
            matches.append(order)
    return matches


def _extract_order_ids(orders: list[dict]) -> list[str]:
    ids: list[str] = []
    for order in orders:
        oid = str(order.get("id") or order.get("order_id") or "")
        if oid:
            ids.append(oid)
    return ids


def _side_matches_broker_position(side: str, signed_qty: float) -> bool:
    side_norm = str(side or "").upper()
    if abs(signed_qty) <= 1e-9:
        return False
    if side_norm == "BUY":
        return signed_qty > 0
    if side_norm == "SELL":
        return signed_qty < 0
    return False


def _build_leg_plan(
    row: TradeLedger,
    *,
    positions: list[dict],
    pending_orders: list[dict],
    order_snapshot: dict | None,
    order_snapshot_error: str | None,
) -> LegReconciliationPlan:
    signed_qty = signed_broker_qty_for_ticker(positions, row.ticker)
    open_orders = _pending_orders_for_row(row, pending_orders)
    return LegReconciliationPlan(
        ledger_id=str(row.id),
        order_id=str(row.order_id) if row.order_id else None,
        ticker=row.ticker,
        side=_enum_value(row.side),
        quantity=float(row.quantity or 0.0),
        price=float(row.price or 0.0),
        status=_enum_value(row.status),
        broker_qty_signed=signed_qty,
        broker_qty_abs=abs(signed_qty),
        open_order_ids=_extract_order_ids(open_orders),
        order_snapshot=order_snapshot,
        order_snapshot_error=order_snapshot_error,
    )


def classify_signal_reconciliation(
    *,
    signal_id: str,
    rows: list[TradeLedger],
    positions: list[dict],
    pending_orders: list[dict],
    order_snapshots: dict[str, dict | None],
    order_snapshot_errors: dict[str, str | None],
    managed_open_tickers: dict[str, set[str]],
) -> SignalReconciliationPlan:
    """Read-only classifier for one signal's unresolved ledger rows."""
    legs = [
        _build_leg_plan(
            row,
            positions=positions,
            pending_orders=pending_orders,
            order_snapshot=order_snapshots.get(str(row.order_id or "")),
            order_snapshot_error=order_snapshot_errors.get(str(row.order_id or "")),
        )
        for row in rows
    ]
    reasons: list[str] = []

    if not rows:
        return SignalReconciliationPlan(
            signal_id=signal_id,
            action=SignalReconciliationAction.MANUAL_REQUIRED,
            legs=legs,
            reasons=["no_rows"],
        )

    if signal_id in {"", "__no_signal__", "None"} or not signal_id:
        reasons.append("missing_signal_id")
        return SignalReconciliationPlan(
            signal_id=signal_id or "__no_signal__",
            action=SignalReconciliationAction.MANUAL_REQUIRED,
            legs=legs,
            reasons=reasons,
        )

    # Symbol collision: another managed open signal already owns a ticker.
    for leg in legs:
        owners = managed_open_tickers.get(normalize_symbol(leg.ticker), set())
        other_owners = {owner for owner in owners if owner != signal_id}
        if other_owners:
            leg.reasons.append(
                f"symbol_collision:{leg.ticker}:owners={','.join(sorted(other_owners))}"
            )
            reasons.append(f"symbol_collision:{leg.ticker}")

    all_flat = all(leg.broker_qty_abs <= 1e-9 for leg in legs)
    any_open_orders = any(leg.open_order_ids for leg in legs)
    if all_flat and not any_open_orders:
        return SignalReconciliationPlan(
            signal_id=signal_id,
            action=SignalReconciliationAction.SAFE_AUTO_CLOSE,
            legs=legs,
            reasons=reasons or ["broker_flat_no_open_orders"],
        )

    if any_open_orders:
        for leg in legs:
            if leg.open_order_ids:
                leg.reasons.append(f"open_orders:{','.join(leg.open_order_ids)}")
        reasons.append("pending_orders_present")

    restore_blockers: list[str] = []
    for leg in legs:
        order_id = str(leg.order_id or "")
        if not order_id or order_id.startswith("ORPHAN_"):
            leg.reasons.append("missing_broker_order_id")
            restore_blockers.append(f"{leg.ticker}:missing_order_id")
            continue
        if leg.order_snapshot_error:
            leg.reasons.append(f"order_snapshot_error:{leg.order_snapshot_error}")
            restore_blockers.append(f"{leg.ticker}:snapshot_error")
            continue
        snap = leg.order_snapshot
        if not snap:
            leg.reasons.append("order_snapshot_missing")
            restore_blockers.append(f"{leg.ticker}:snapshot_missing")
            continue

        status = str(snap.get("status") or "").lower()
        filled_qty = float(snap.get("filled_qty") or snap.get("quantity") or 0.0)
        fill_price = float(snap.get("filled_avg_price") or snap.get("limitPrice") or leg.price or 0.0)
        expected_notional = float(leg.quantity or 0.0) * float(leg.price or 0.0)
        fill_complete = is_broker_fill_complete(
            status=status,
            filled_qty=filled_qty,
            expected_qty=float(leg.quantity or 0.0),
            fill_price=fill_price,
            expected_notional=expected_notional,
        )
        if not fill_complete:
            leg.reasons.append(f"order_not_fully_filled:status={status}:filled_qty={filled_qty}")
            restore_blockers.append(f"{leg.ticker}:incomplete_fill")
            continue

        if leg.broker_qty_abs <= 1e-9:
            leg.reasons.append("broker_flat_but_order_filled")
            restore_blockers.append(f"{leg.ticker}:flat_after_fill")
            continue

        if not _side_matches_broker_position(leg.side, leg.broker_qty_signed):
            leg.reasons.append(
                f"broker_direction_mismatch:side={leg.side}:signed_qty={leg.broker_qty_signed}"
            )
            restore_blockers.append(f"{leg.ticker}:direction_mismatch")
            continue

        if leg.broker_qty_abs + 1e-9 < filled_qty * 0.95:
            leg.reasons.append(
                f"broker_qty_below_fill:filled_qty={filled_qty}:broker_qty={leg.broker_qty_abs}"
            )
            restore_blockers.append(f"{leg.ticker}:qty_below_fill")

    if restore_blockers:
        reasons.extend(restore_blockers)
        return SignalReconciliationPlan(
            signal_id=signal_id,
            action=SignalReconciliationAction.MANUAL_REQUIRED,
            legs=legs,
            reasons=reasons or ["restore_checks_failed"],
        )

    if len(legs) >= 2 and not any_open_orders:
        return SignalReconciliationPlan(
            signal_id=signal_id,
            action=SignalReconciliationAction.SAFE_AUTO_RESTORE_OPEN,
            legs=legs,
            reasons=reasons or ["both_legs_filled_positions_match"],
        )

    if len(legs) < 2:
        reasons.append("single_leg_signal")
    else:
        reasons.append("restore_precheck_failed")
    return SignalReconciliationPlan(
        signal_id=signal_id,
        action=SignalReconciliationAction.MANUAL_REQUIRED,
        legs=legs,
        reasons=reasons,
    )


async def _fetch_order_snapshots(
    brokerage,
    rows: list[TradeLedger],
) -> tuple[dict[str, dict | None], dict[str, str | None]]:
    snapshots: dict[str, dict | None] = {}
    errors: dict[str, str | None] = {}
    get_order = getattr(brokerage, "get_order", None)
    if not get_order:
        for row in rows:
            order_id = str(row.order_id or "")
            if order_id:
                errors[order_id] = "broker_get_order_unavailable"
        return snapshots, errors

    seen: set[str] = set()
    for row in rows:
        order_id = str(row.order_id or "")
        if not order_id or order_id.startswith("ORPHAN_") or order_id in seen:
            continue
        seen.add(order_id)
        try:
            snapshots[order_id] = await _maybe_await(get_order(order_id))
            errors[order_id] = None
        except Exception as exc:
            snapshots[order_id] = None
            errors[order_id] = str(exc)
    return snapshots, errors


async def _managed_open_ticker_map(exclude_signal_ids: set[str]) -> dict[str, set[str]]:
    managed: dict[str, set[str]] = {}
    try:
        open_signals = await persistence_service.get_open_signals()
    except Exception:
        return managed
    for signal in open_signals or []:
        signal_id = str(signal.get("signal_id") or "")
        if not signal_id or signal_id in exclude_signal_ids:
            continue
        for leg in signal.get("legs", []):
            canonical = normalize_symbol(leg.get("ticker") or "")
            if canonical:
                managed.setdefault(canonical, set()).add(signal_id)
    return managed


async def plan_signal_level_reconciliation(
    *,
    brokerage,
) -> dict[str, Any]:
    """Read-only planner: group unresolved rows by signal_id and classify recovery."""
    async with persistence_service.AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(TradeLedger)
                .where(TradeLedger.status.in_(persistence_service._startup_unresolved_statuses()))
                .where(TradeLedger.closed_at.is_(None))
            )
        ).scalars().all()

    if not rows:
        return {
            "examined_rows": 0,
            "signal_count": 0,
            "broker_ok": True,
            "plans": [],
            "summary": {
                SignalReconciliationAction.SAFE_AUTO_CLOSE.value: 0,
                SignalReconciliationAction.SAFE_AUTO_RESTORE_OPEN.value: 0,
                SignalReconciliationAction.MANUAL_REQUIRED.value: 0,
            },
        }

    try:
        positions = list(await _maybe_await(brokerage.get_portfolio()) or [])
        pending_orders = list(await _maybe_await(brokerage.get_pending_orders()) or [])
        broker_ok = True
        broker_error: str | None = None
    except Exception as exc:
        broker_ok = False
        broker_error = str(exc)
        positions = []
        pending_orders = []
        logger.error("Signal reconciliation planner aborted broker read: %s", exc)

    order_snapshots, order_snapshot_errors = (
        await _fetch_order_snapshots(brokerage, rows) if broker_ok else ({}, {})
    )

    grouped: dict[str, list[TradeLedger]] = {}
    for row in rows:
        signal_key = str(row.signal_id) if row.signal_id else "__no_signal__"
        grouped.setdefault(signal_key, []).append(row)

    exclude_signal_ids = set(grouped.keys()) - {"__no_signal__"}
    managed_open_tickers = await _managed_open_ticker_map(exclude_signal_ids)

    plans: list[SignalReconciliationPlan] = []
    for signal_id, signal_rows in sorted(grouped.items()):
        plan = classify_signal_reconciliation(
            signal_id=signal_id,
            rows=signal_rows,
            positions=positions,
            pending_orders=pending_orders,
            order_snapshots=order_snapshots,
            order_snapshot_errors=order_snapshot_errors,
            managed_open_tickers=managed_open_tickers,
        )
        if not broker_ok:
            plan.action = SignalReconciliationAction.MANUAL_REQUIRED
            plan.reasons = [f"broker_read_failed:{broker_error}"] + list(plan.reasons)
        plans.append(plan)

    summary = {
        SignalReconciliationAction.SAFE_AUTO_CLOSE.value: 0,
        SignalReconciliationAction.SAFE_AUTO_RESTORE_OPEN.value: 0,
        SignalReconciliationAction.MANUAL_REQUIRED.value: 0,
    }
    for plan in plans:
        summary[plan.action.value] += 1

    return {
        "examined_rows": len(rows),
        "signal_count": len(plans),
        "broker_ok": broker_ok,
        "broker_error": broker_error,
        "plans": plans,
        "summary": summary,
    }


def format_signal_reconciliation_plan(plan: SignalReconciliationPlan) -> str:
    leg_bits = []
    for leg in plan.legs:
        snap_status = ""
        if leg.order_snapshot:
            snap_status = str(leg.order_snapshot.get("status") or "")
        leg_bits.append(
            "ledger_id={ledger_id} ticker={ticker} side={side} qty={quantity} "
            "status={status} broker_qty_signed={broker_qty_signed} "
            "open_order_ids={open_order_ids} order_status={order_status} "
            "order_snapshot_error={order_snapshot_error} leg_reasons={leg_reasons}".format(
                ledger_id=leg.ledger_id,
                ticker=leg.ticker,
                side=leg.side,
                quantity=leg.quantity,
                status=leg.status,
                broker_qty_signed=leg.broker_qty_signed,
                open_order_ids=leg.open_order_ids,
                order_status=snap_status,
                order_snapshot_error=leg.order_snapshot_error,
                leg_reasons=",".join(leg.reasons) if leg.reasons else "none",
            )
        )
    return (
        f"signal_id={plan.signal_id} action={plan.action.value} "
        f"reasons={','.join(plan.reasons) if plan.reasons else 'none'} "
        f"legs=[{' | '.join(leg_bits)}]"
    )


def log_signal_reconciliation_plans(result: dict[str, Any]) -> None:
    if not result.get("plans"):
        logger.info(
            "Signal reconciliation planner: no unresolved rows (examined_rows=%s).",
            result.get("examined_rows", 0),
        )
        return
    logger.info(
        "Signal reconciliation planner: examined_rows=%s signal_count=%s broker_ok=%s summary=%s",
        result.get("examined_rows"),
        result.get("signal_count"),
        result.get("broker_ok"),
        result.get("summary"),
    )
    for plan in result.get("plans", []):
        logger.info("Signal reconciliation plan: %s", format_signal_reconciliation_plan(plan))


def signal_reconciliation_plan_to_dict(plan: SignalReconciliationPlan) -> dict[str, Any]:
    payload = asdict(plan)
    payload["action"] = plan.action.value
    return payload

BROKER_CONFIRMED_RECONCILE_STATUSES = (
    OrderStatus.NEEDS_MANUAL_RECONCILIATION,
    OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
)

_FILL_QTY_TOLERANCE_ABS = 1e-9
_FILL_QTY_TOLERANCE_REL = 0.001


def _is_broker_confirmed_reconcile_status(row: TradeLedger) -> bool:
    status = row.status
    status_value = status.value if isinstance(status, OrderStatus) else str(status)
    return status in BROKER_CONFIRMED_RECONCILE_STATUSES or status_value in {
        s.value for s in BROKER_CONFIRMED_RECONCILE_STATUSES
    }


def _broker_order_id(row: TradeLedger) -> str:
    meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return str(row.order_id or meta.get("broker_order_id") or "")


def _expected_filled_qty(row: TradeLedger) -> float:
    meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    for key in ("filled_qty", "submitted_qty"):
        value = meta.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    try:
        return float(row.quantity or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _qty_matches(expected: float, actual: float) -> bool:
    if expected <= 0:
        return abs(actual) <= _FILL_QTY_TOLERANCE_ABS
    tolerance = max(_FILL_QTY_TOLERANCE_ABS, abs(expected) * _FILL_QTY_TOLERANCE_REL)
    return abs(actual - expected) <= tolerance


def _order_is_filled(order: dict) -> bool:
    return str(order.get("status") or "").lower() == "filled"


def _group_rows_by_signal(rows: list[TradeLedger]) -> dict[str, list[TradeLedger]]:
    grouped: dict[str, list[TradeLedger]] = {}
    for row in rows:
        signal_id = str(row.signal_id or "")
        if not signal_id:
            continue
        grouped.setdefault(signal_id, []).append(row)
    return grouped


async def auto_reconcile_broker_confirmed_pairs(
    *,
    brokerage,
    dry_run: bool = False,
) -> dict:
    """Restore OPEN_PAIR when broker confirms both legs filled for a stuck signal.

    Safe only for two-leg pair rows in manual-reconciliation statuses where every
    leg order_id is terminal filled on the broker with quantities matching ledger.
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
            return {
                "examined": 0,
                "restored": 0,
                "blocked": 0,
                "signals_examined": 0,
                "broker_ok": True,
            }

        grouped = _group_rows_by_signal(list(rows))
        restored = 0
        blocked = 0
        signals_examined = 0
        now = datetime.now(timezone.utc)

        for signal_id, legs in grouped.items():
            signals_examined += 1
            if len(legs) != 2:
                blocked += len(legs)
                logger.info(
                    "Auto-reconcile skip signal_id=%s: expected 2 legs, found %s",
                    signal_id,
                    len(legs),
                )
                continue
            if not all(_is_broker_confirmed_reconcile_status(leg) for leg in legs):
                blocked += len(legs)
                continue

            order_ids = [_broker_order_id(leg) for leg in legs]
            if not all(order_ids):
                blocked += len(legs)
                logger.info(
                    "Auto-reconcile skip signal_id=%s: missing broker order id on one or more legs",
                    signal_id,
                )
                continue

            try:
                broker_orders = [await _maybe_await(brokerage.get_order(oid)) for oid in order_ids]
            except Exception as exc:
                blocked += len(legs)
                logger.warning(
                    "Auto-reconcile skip signal_id=%s: broker order lookup failed: %s",
                    signal_id,
                    exc,
                )
                continue

            if not all(_order_is_filled(order) for order in broker_orders):
                blocked += len(legs)
                logger.info(
                    "Auto-reconcile skip signal_id=%s: broker orders not all filled statuses=%s",
                    signal_id,
                    [str(o.get("status")) for o in broker_orders],
                )
                continue

            qty_ok = True
            for leg, broker_order in zip(legs, broker_orders):
                expected = _expected_filled_qty(leg)
                actual = float(broker_order.get("filled_qty") or 0.0)
                if not _qty_matches(expected, actual):
                    qty_ok = False
                    logger.info(
                        "Auto-reconcile skip signal_id=%s leg=%s: qty mismatch expected=%s broker=%s",
                        signal_id,
                        leg.ticker,
                        expected,
                        actual,
                    )
                    break
            if not qty_ok:
                blocked += len(legs)
                continue

            if dry_run:
                restored += len(legs)
                continue

            for leg, broker_order, order_id in zip(legs, broker_orders, order_ids):
                meta = dict(leg.metadata_json or {})
                meta["auto_reconciliation"] = {
                    "method": "auto_reconcile_broker_confirmed_pairs",
                    "reconciled_at": now.isoformat(),
                    "broker_order_id": order_id,
                    "broker_status": str(broker_order.get("status")),
                    "broker_filled_qty": float(broker_order.get("filled_qty") or 0.0),
                    "broker_filled_avg_price": float(broker_order.get("filled_avg_price") or 0.0),
                    "previous_status": (
                        leg.status.value if isinstance(leg.status, OrderStatus) else str(leg.status)
                    ),
                }
                meta["pair_status"] = OrderStatus.OPEN_PAIR.value
                leg.status = OrderStatus.OPEN_PAIR
                leg.quantity = float(broker_order.get("filled_qty") or leg.quantity or 0.0)
                avg_price = float(broker_order.get("filled_avg_price") or 0.0)
                if avg_price > 0:
                    leg.price = avg_price
                leg.metadata_json = meta
                session.add(leg)
                restored += 1
                logger.info(
                    "Auto-reconcile restored OPEN_PAIR signal_id=%s ledger_id=%s ticker=%s order_id=%s",
                    signal_id,
                    leg.id,
                    leg.ticker,
                    order_id,
                )

        if not dry_run and restored:
            await session.commit()

        return {
            "examined": len(rows),
            "restored": restored,
            "blocked": blocked,
            "signals_examined": signals_examined,
            "broker_ok": True,
        }

