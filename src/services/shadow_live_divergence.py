"""Permanent Shadow vs LIVE divergence monitor (Phase-5).

When LIVE (or broker-paper) is active, a parallel shadow decision trail can be
compared on the same scan inputs. Divergences are fail-loud alerts — they do
not auto-mutate LIVE orders.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DivergenceEvent:
    ts: str
    pair_id: str
    signal_id: Optional[str]
    live_decision: str
    shadow_decision: str
    live_confidence: Optional[float]
    shadow_confidence: Optional[float]
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ShadowLiveDivergenceMonitor:
    """In-process divergence ring; persist via alert hooks."""

    def __init__(self, *, maxlen: int = 500):
        self._events: Deque[DivergenceEvent] = deque(maxlen=maxlen)
        self._live_by_pair: Dict[str, dict] = {}
        self._shadow_by_pair: Dict[str, dict] = {}

    def record_live(
        self,
        *,
        pair_id: str,
        decision: str,
        confidence: Optional[float] = None,
        signal_id: Optional[str] = None,
        inputs: Optional[dict] = None,
    ) -> None:
        self._live_by_pair[pair_id] = {
            "decision": str(decision),
            "confidence": confidence,
            "signal_id": signal_id,
            "inputs": dict(inputs or {}),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._maybe_compare(pair_id)

    def record_shadow(
        self,
        *,
        pair_id: str,
        decision: str,
        confidence: Optional[float] = None,
        signal_id: Optional[str] = None,
        inputs: Optional[dict] = None,
    ) -> None:
        self._shadow_by_pair[pair_id] = {
            "decision": str(decision),
            "confidence": confidence,
            "signal_id": signal_id,
            "inputs": dict(inputs or {}),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._maybe_compare(pair_id)

    def _maybe_compare(self, pair_id: str) -> Optional[DivergenceEvent]:
        live = self._live_by_pair.get(pair_id)
        shadow = self._shadow_by_pair.get(pair_id)
        if not live or not shadow:
            return None
        # Only compare when both sides have fresh stamps within the same scan window
        # (caller should clear between scans if needed).
        if live["decision"] == shadow["decision"]:
            # Confidence drift > 15pp still alerts.
            lc = live.get("confidence")
            sc = shadow.get("confidence")
            if lc is not None and sc is not None and abs(float(lc) - float(sc)) < 0.15:
                return None
            if lc is None or sc is None:
                return None
            reason = "confidence_divergence"
        else:
            reason = "decision_divergence"

        event = DivergenceEvent(
            ts=datetime.now(timezone.utc).isoformat(),
            pair_id=pair_id,
            signal_id=live.get("signal_id") or shadow.get("signal_id"),
            live_decision=str(live["decision"]),
            shadow_decision=str(shadow["decision"]),
            live_confidence=_as_float(live.get("confidence")),
            shadow_confidence=_as_float(shadow.get("confidence")),
            reason=reason,
            details={
                "live_inputs_hash": _hash_obj(live.get("inputs")),
                "shadow_inputs_hash": _hash_obj(shadow.get("inputs")),
            },
        )
        self._events.append(event)
        logger.warning(
            "SHADOW/LIVE DIVERGENCE pair=%s reason=%s live=%s shadow=%s",
            pair_id,
            reason,
            live["decision"],
            shadow["decision"],
        )
        return event

    def clear_pair(self, pair_id: str) -> None:
        self._live_by_pair.pop(pair_id, None)
        self._shadow_by_pair.pop(pair_id, None)

    def recent(self, limit: int = 50) -> List[dict]:
        items = list(self._events)[-limit:]
        return [e.to_dict() for e in items]

    def divergence_count(self) -> int:
        return len(self._events)


def _as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _hash_obj(obj: Any) -> str:
    encoded = json.dumps(obj or {}, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()[:12]


shadow_live_divergence_monitor = ShadowLiveDivergenceMonitor()
