"""Shadow vs broker-paper vs live execution lane helpers.

PAPER_TRADING=true → SHADOW (simulated fills via shadow_service; no broker orders).
PAPER_TRADING=false + Alpaca paper API → BROKER_PAPER (real paper orders).
Otherwise → LIVE (real-money broker path).

Ledger closes must follow how a position was *opened* (metadata), not only the
current env flag, so mode flips cannot double-submit broker closes or orphan fills.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

LANE_SHADOW = "SHADOW"
LANE_BROKER_PAPER = "BROKER_PAPER"
LANE_LIVE = "LIVE"


def resolve_execution_lane(
    *,
    paper_trading: bool,
    broker_paper_trading: bool,
) -> str:
    if paper_trading:
        return LANE_SHADOW
    if broker_paper_trading:
        return LANE_BROKER_PAPER
    return LANE_LIVE


def _leg_metadata(leg: Mapping[str, Any]) -> dict:
    meta = leg.get("metadata")
    if meta is None:
        meta = leg.get("metadata_json")
    return meta if isinstance(meta, dict) else {}


def signal_is_shadow(signal: Mapping[str, Any]) -> bool:
    """True when the open signal was opened on the shadow lane."""
    if signal.get("is_shadow") is True:
        return True
    if signal.get("execution_lane") == LANE_SHADOW:
        return True
    for leg in signal.get("legs") or []:
        if not isinstance(leg, Mapping):
            continue
        if leg.get("is_shadow") is True:
            return True
        meta = _leg_metadata(leg)
        if meta.get("is_shadow") is True:
            return True
        if meta.get("execution_lane") == LANE_SHADOW:
            return True
    return False


def signal_has_explicit_lane(signal: Mapping[str, Any]) -> bool:
    """True when at least one leg (or the signal) carries lane / is_shadow metadata."""
    if signal.get("execution_lane") in (LANE_SHADOW, LANE_BROKER_PAPER, LANE_LIVE):
        return True
    if signal.get("is_shadow") is not None:
        return True
    for leg in signal.get("legs") or []:
        if not isinstance(leg, Mapping):
            continue
        if leg.get("is_shadow") is not None:
            return True
        meta = _leg_metadata(leg)
        if meta.get("is_shadow") is not None:
            return True
        if meta.get("execution_lane") in (LANE_SHADOW, LANE_BROKER_PAPER, LANE_LIVE):
            return True
    return False


def close_uses_broker(
    signal: Mapping[str, Any],
    *,
    paper_trading: bool,
) -> bool:
    """Whether _close_position should place broker close orders.

    Prefer ledger metadata from open; fall back to current PAPER_TRADING only for
    untagged legacy rows.
    """
    if signal_is_shadow(signal):
        return False
    if signal_has_explicit_lane(signal):
        # Explicit non-shadow (broker paper or live) — always close via broker.
        return True
    return not paper_trading


def stamp_trade_metadata(
    metadata: Optional[Mapping[str, Any]],
    *,
    execution_lane: str,
    broker_paper_trading: bool,
) -> dict:
    """Ensure ledger metadata carries a single execution lane (no dual tagging)."""
    meta = dict(metadata) if isinstance(metadata, Mapping) else {}
    is_shadow = bool(meta.get("is_shadow", execution_lane == LANE_SHADOW))
    if is_shadow:
        lane = LANE_SHADOW
    else:
        lane = meta.get("execution_lane") or execution_lane
        if lane == LANE_SHADOW:
            # Caller said not shadow but left lane=SHADOW — coerce to current non-shadow lane.
            lane = execution_lane if execution_lane != LANE_SHADOW else LANE_LIVE
    meta["is_shadow"] = is_shadow
    meta["execution_lane"] = lane
    meta["broker_paper_trading"] = bool(broker_paper_trading) and not is_shadow
    return meta
