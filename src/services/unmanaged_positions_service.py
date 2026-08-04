"""Operator path for broker holdings outside the bot ledger.

Does **not** create OPEN pair signals (which would trigger false exits).
Instead, acknowledgements are stored in system state with clear provenance so
startup risk alerts / fail-closed guards can treat them as operator-reviewed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from src.services.ledger_reconcile_service import position_quantity, symbols_match
from src.services.persistence_service import persistence_service
from src.services.portfolio_book_guards import canonical_book_symbol

logger = logging.getLogger(__name__)

ACK_STATE_KEY = "unmanaged_positions_acknowledged"
ALERT_STATE_KEY = "unmanaged_broker_positions"


def _canonical(symbol: str) -> str:
    """Match monitor / Alpaca ledger keys (BTC-USD and BTCUSD -> BTCUSD)."""
    return canonical_book_symbol(symbol)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonicalize_ack_symbols(symbols: dict[str, Any]) -> dict[str, Any]:
    """Re-key ack map under stripped canonical forms; keep latest meta on collision."""
    out: dict[str, Any] = {}
    for raw_key, meta in (symbols or {}).items():
        canonical = _canonical(str(raw_key))
        if not canonical:
            continue
        entry = dict(meta) if isinstance(meta, dict) else {"symbol": raw_key}
        entry.setdefault("symbol", raw_key)
        entry["canonical"] = canonical
        # Prefer the richer / newer entry when aliases collide.
        prev = out.get(canonical)
        if prev is None:
            out[canonical] = entry
            continue
        prev_ts = str(prev.get("acknowledged_at") or "")
        new_ts = str(entry.get("acknowledged_at") or "")
        out[canonical] = entry if new_ts >= prev_ts else prev
    return out


def parse_acknowledgements(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {"symbols": {}, "updated_at": None}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Corrupt unmanaged acknowledgement payload; resetting.")
        return {"symbols": {}, "updated_at": None}
    symbols = payload.get("symbols") if isinstance(payload, dict) else None
    if not isinstance(symbols, dict):
        return {"symbols": {}, "updated_at": None}
    return {
        "symbols": _canonicalize_ack_symbols(symbols),
        "updated_at": payload.get("updated_at"),
        "actor": payload.get("actor"),
        "note": payload.get("note"),
    }


async def load_acknowledgements() -> dict[str, Any]:
    raw = await persistence_service.get_system_state(ACK_STATE_KEY, default="")
    return parse_acknowledgements(raw)


async def save_acknowledgements(payload: dict[str, Any]) -> None:
    """Persist full ack payload (no mid-JSON truncation — that wiped acks silently)."""
    symbols = _canonicalize_ack_symbols(payload.get("symbols") or {})
    to_store = {
        "symbols": symbols,
        "updated_at": payload.get("updated_at"),
        "actor": payload.get("actor"),
        "note": payload.get("note"),
    }
    encoded = json.dumps(to_store, separators=(",", ":"), default=str)
    if len(encoded) > 200_000:
        logger.error(
            "Unmanaged ack payload unusually large (%d bytes, %d symbols); still persisting.",
            len(encoded),
            len(symbols),
        )
    await persistence_service.set_system_state(ACK_STATE_KEY, encoded)


async def sync_alert_state_after_ack(acknowledgements: dict[str, Any]) -> None:
    """Replace stale RISK ALERT snapshot with acknowledged-only operator state."""
    symbols = sorted((acknowledgements or {}).get("symbols") or {})
    if not symbols:
        await persistence_service.set_system_state(ALERT_STATE_KEY, "")
        return
    payload = {
        "ignored": True,
        "auto_flatten": False,
        "acknowledged_only": True,
        "count": len(symbols),
        "symbols": symbols,
        "updated_at": (acknowledgements or {}).get("updated_at") or _utc_now_iso(),
    }
    await persistence_service.set_system_state(
        ALERT_STATE_KEY,
        json.dumps(payload, separators=(",", ":"), default=str),
    )


def broker_position_snapshot(position: dict) -> dict[str, Any]:
    raw_symbol = (
        position.get("ticker")
        or position.get("symbol")
        or position.get("instrumentTicker")
        or position.get("instrument")
        or ""
    )
    qty = position_quantity(position)
    return {
        "symbol": str(raw_symbol),
        "canonical": _canonical(str(raw_symbol)),
        "quantity": qty,
        "avg_price": position.get("averagePrice") or position.get("avg_price") or position.get("avg_entry_price"),
        "current_price": position.get("currentPrice") or position.get("current_price"),
        "market_value": position.get("marketValue") or position.get("market_value"),
    }


def ledger_managed_symbols(open_signals: Iterable[dict]) -> set[str]:
    managed: set[str] = set()
    for signal in open_signals or []:
        for leg in signal.get("legs", []) or []:
            canonical = _canonical(str(leg.get("ticker") or ""))
            if canonical:
                managed.add(canonical)
    return managed


def classify_broker_positions(
    broker_positions: Iterable[dict],
    open_signals: Iterable[dict],
    acknowledgements: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Split broker inventory into managed / unmanaged / acknowledged."""
    managed = ledger_managed_symbols(open_signals)
    ack_symbols = (acknowledgements or {}).get("symbols") or {}
    ack_keys = list(ack_symbols.keys())

    unmanaged: list[dict[str, Any]] = []
    acknowledged: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []

    for position in broker_positions or []:
        snap = broker_position_snapshot(position)
        if abs(float(snap["quantity"] or 0.0)) <= 1e-12:
            continue
        canonical = snap["canonical"]
        if not canonical:
            continue
        if canonical in managed or any(symbols_match(canonical, m) for m in managed):
            matched.append({**snap, "status": "managed"})
            continue
        ack_key = next((key for key in ack_keys if symbols_match(canonical, key)), None)
        if ack_key is not None:
            ack_meta = ack_symbols.get(ack_key) or {}
            acknowledged.append({**snap, "status": "acknowledged", "ack": ack_meta})
            continue
        unmanaged.append({**snap, "status": "unmanaged"})

    return {
        "managed": matched,
        "unmanaged": unmanaged,
        "acknowledged": acknowledged,
        "unmanaged_symbols": [row["symbol"] for row in unmanaged],
        "acknowledged_symbols": [row["symbol"] for row in acknowledged],
    }


def filter_unacked_symbols(
    unmanaged_symbols: Iterable[str],
    acknowledgements: Optional[dict[str, Any]],
) -> list[str]:
    ack_symbols = (acknowledgements or {}).get("symbols") or {}
    ack_keys = list(ack_symbols.keys())
    remaining: list[str] = []
    for symbol in unmanaged_symbols or []:
        if any(symbols_match(str(symbol), key) for key in ack_keys):
            continue
        remaining.append(str(symbol))
    return remaining


async def acknowledge_symbols(
    *,
    symbols: list[str],
    positions: Optional[Iterable[dict]] = None,
    actor: str = "dashboard",
    note: str = "",
    replace: bool = False,
) -> dict[str, Any]:
    """Mark broker symbols as operator-acknowledged unmanaged holdings.

    Provenance is stored only in system state — never as OPEN trade-ledger rows.
    """
    current = await load_acknowledgements()
    symbols_map: dict[str, Any] = {} if replace else dict(current.get("symbols") or {})

    position_by_canonical: dict[str, dict] = {}
    for position in positions or []:
        snap = broker_position_snapshot(position)
        if snap["canonical"]:
            position_by_canonical[snap["canonical"]] = snap

    acknowledged_now: list[str] = []
    for raw in symbols:
        canonical = _canonical(raw)
        if not canonical:
            continue
        snap = position_by_canonical.get(canonical, {"symbol": raw, "canonical": canonical})
        symbols_map[canonical] = {
            "symbol": snap.get("symbol") or raw,
            "quantity": snap.get("quantity"),
            "market_value": snap.get("market_value"),
            "acknowledged_at": _utc_now_iso(),
            "actor": actor,
            "note": note or "operator_acknowledged_unmanaged",
            "provenance": "broker_foreign_holding",
        }
        acknowledged_now.append(canonical)

    payload = {
        "symbols": symbols_map,
        "updated_at": _utc_now_iso(),
        "actor": actor,
        "note": note or "operator_acknowledged_unmanaged",
    }
    await save_acknowledgements(payload)
    await sync_alert_state_after_ack(payload)
    logger.info(
        "Acknowledged %d unmanaged broker symbol(s): %s (actor=%s)",
        len(acknowledged_now),
        ", ".join(acknowledged_now),
        actor,
    )
    return payload


async def clear_acknowledgements(*, symbols: Optional[list[str]] = None) -> dict[str, Any]:
    current = await load_acknowledgements()
    if not symbols:
        empty = {"symbols": {}, "updated_at": _utc_now_iso(), "actor": None, "note": "cleared"}
        await save_acknowledgements(empty)
        await sync_alert_state_after_ack(empty)
        return empty

    symbols_map = dict(current.get("symbols") or {})
    for raw in symbols:
        canonical = _canonical(raw)
        # Drop exact canonical key and any alias that symbols_match would treat as equal.
        drop_keys = [
            key
            for key in list(symbols_map.keys())
            if key == canonical or symbols_match(str(raw), key)
        ]
        for key in drop_keys:
            symbols_map.pop(key, None)
    payload = {
        "symbols": symbols_map,
        "updated_at": _utc_now_iso(),
        "actor": current.get("actor"),
        "note": "partial_clear",
    }
    await save_acknowledgements(payload)
    await sync_alert_state_after_ack(payload)
    return payload


unmanaged_positions_service = type(
    "UnmanagedPositionsService",
    (),
    {
        "load_acknowledgements": staticmethod(load_acknowledgements),
        "acknowledge_symbols": staticmethod(acknowledge_symbols),
        "clear_acknowledgements": staticmethod(clear_acknowledgements),
        "classify_broker_positions": staticmethod(classify_broker_positions),
        "filter_unacked_symbols": staticmethod(filter_unacked_symbols),
        "sync_alert_state_after_ack": staticmethod(sync_alert_state_after_ack),
    },
)()
