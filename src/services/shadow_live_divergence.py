"""Shadow vs LIVE divergence with severity classes (Phase-5 revision).

Severity policy (operator guidance):
  INFO     — record only (e.g. sub-second timestamp skew)
  WARNING  — requires reconciliation attention (PnL calc / confidence drift)
  CRITICAL — block new entries (decision disagreement that could open risk)
  FATAL    — halt system / flatten per risk policy (position/qty/risk-state mismatch)

A pile of INFO/WARNING events must not stop the bot; a single FATAL must.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


class DivergenceSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"


# Kind → default severity. Callers may override.
_KIND_SEVERITY: dict[str, DivergenceSeverity] = {
    "timestamp_skew": DivergenceSeverity.INFO,
    "confidence_divergence": DivergenceSeverity.WARNING,
    "pnl_calc_divergence": DivergenceSeverity.WARNING,
    "decision_divergence": DivergenceSeverity.CRITICAL,
    "open_position_mismatch": DivergenceSeverity.FATAL,
    "quantity_mismatch": DivergenceSeverity.FATAL,
    "risk_state_divergence": DivergenceSeverity.FATAL,
}


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
    severity: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def classify_divergence_kind(
    *,
    kind: str,
    timestamp_skew_ms: Optional[float] = None,
    severity_override: Optional[DivergenceSeverity] = None,
) -> DivergenceSeverity:
    if severity_override is not None:
        return severity_override
    if kind == "timestamp_skew":
        skew = float(timestamp_skew_ms or 0.0)
        if skew < 500:
            return DivergenceSeverity.INFO
        if skew < 5000:
            return DivergenceSeverity.WARNING
        return DivergenceSeverity.CRITICAL
    return _KIND_SEVERITY.get(kind, DivergenceSeverity.WARNING)


class ShadowLiveDivergenceMonitor:
    """In-process divergence ring with severity-aware policy hooks."""

    def __init__(self, *, maxlen: int = 500):
        self._events: Deque[DivergenceEvent] = deque(maxlen=maxlen)
        self._live_by_pair: Dict[str, dict] = {}
        self._shadow_by_pair: Dict[str, dict] = {}
        self._counts: Dict[str, int] = {s.value: 0 for s in DivergenceSeverity}

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

    def record_state_divergence(
        self,
        *,
        pair_id: str,
        kind: str,
        live_value: Any,
        shadow_value: Any,
        signal_id: Optional[str] = None,
        timestamp_skew_ms: Optional[float] = None,
        severity_override: Optional[DivergenceSeverity] = None,
        details: Optional[dict] = None,
    ) -> DivergenceEvent:
        """Explicit position/qty/risk/pnl/timestamp divergence (preferred for FATAL)."""
        severity = classify_divergence_kind(
            kind=kind,
            timestamp_skew_ms=timestamp_skew_ms,
            severity_override=severity_override,
        )
        event = DivergenceEvent(
            ts=datetime.now(timezone.utc).isoformat(),
            pair_id=pair_id,
            signal_id=signal_id,
            live_decision=str(live_value),
            shadow_decision=str(shadow_value),
            live_confidence=None,
            shadow_confidence=None,
            reason=kind,
            severity=severity.value,
            details={
                "live_value": live_value,
                "shadow_value": shadow_value,
                **(details or {}),
            },
        )
        self._emit(event)
        return event

    def _maybe_compare(self, pair_id: str) -> Optional[DivergenceEvent]:
        live = self._live_by_pair.get(pair_id)
        shadow = self._shadow_by_pair.get(pair_id)
        if not live or not shadow:
            return None

        skew_ms = None
        try:
            from dateutil.parser import isoparse  # optional

            skew_ms = abs(
                (isoparse(live["ts"]) - isoparse(shadow["ts"])).total_seconds() * 1000
            )
        except Exception:  # noqa: BLE001
            try:
                # Fallback without dateutil
                skew_ms = abs(
                    (
                        datetime.fromisoformat(live["ts"].replace("Z", "+00:00"))
                        - datetime.fromisoformat(shadow["ts"].replace("Z", "+00:00"))
                    ).total_seconds()
                    * 1000
                )
            except Exception:  # noqa: BLE001
                skew_ms = None

        if live["decision"] == shadow["decision"]:
            lc = live.get("confidence")
            sc = shadow.get("confidence")
            if lc is not None and sc is not None and abs(float(lc) - float(sc)) >= 0.15:
                kind = "confidence_divergence"
            elif skew_ms is not None and skew_ms >= 200:
                kind = "timestamp_skew"
            else:
                return None
        else:
            kind = "decision_divergence"

        severity = classify_divergence_kind(kind=kind, timestamp_skew_ms=skew_ms)
        event = DivergenceEvent(
            ts=datetime.now(timezone.utc).isoformat(),
            pair_id=pair_id,
            signal_id=live.get("signal_id") or shadow.get("signal_id"),
            live_decision=str(live["decision"]),
            shadow_decision=str(shadow["decision"]),
            live_confidence=_as_float(live.get("confidence")),
            shadow_confidence=_as_float(shadow.get("confidence")),
            reason=kind,
            severity=severity.value,
            details={
                "live_inputs_hash": _hash_obj(live.get("inputs")),
                "shadow_inputs_hash": _hash_obj(shadow.get("inputs")),
                "timestamp_skew_ms": skew_ms,
            },
        )
        self._emit(event)
        return event

    def _emit(self, event: DivergenceEvent) -> None:
        self._events.append(event)
        self._counts[event.severity] = self._counts.get(event.severity, 0) + 1
        log_fn = {
            DivergenceSeverity.INFO.value: logger.info,
            DivergenceSeverity.WARNING.value: logger.warning,
            DivergenceSeverity.CRITICAL.value: logger.error,
            DivergenceSeverity.FATAL.value: logger.critical,
        }.get(event.severity, logger.warning)
        log_fn(
            "SHADOW/LIVE DIVERGENCE severity=%s pair=%s reason=%s live=%s shadow=%s",
            event.severity,
            event.pair_id,
            event.reason,
            event.live_decision,
            event.shadow_decision,
        )

    def clear_pair(self, pair_id: str) -> None:
        self._live_by_pair.pop(pair_id, None)
        self._shadow_by_pair.pop(pair_id, None)

    def recent(self, limit: int = 50) -> List[dict]:
        items = list(self._events)[-limit:]
        return [e.to_dict() for e in items]

    def divergence_count(self) -> int:
        """Total events (all severities) — prefer severity_counts() for policy."""
        return len(self._events)

    def severity_counts(self) -> Dict[str, int]:
        return dict(self._counts)

    def has_severity_at_least(self, minimum: DivergenceSeverity) -> bool:
        order = [
            DivergenceSeverity.INFO,
            DivergenceSeverity.WARNING,
            DivergenceSeverity.CRITICAL,
            DivergenceSeverity.FATAL,
        ]
        min_idx = order.index(minimum)
        for sev in order[min_idx:]:
            if self._counts.get(sev.value, 0) > 0:
                return True
        return False

    def highest_severity(self) -> Optional[str]:
        for sev in (
            DivergenceSeverity.FATAL,
            DivergenceSeverity.CRITICAL,
            DivergenceSeverity.WARNING,
            DivergenceSeverity.INFO,
        ):
            if self._counts.get(sev.value, 0) > 0:
                return sev.value
        return None


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
