"""Decision Flight Recorder — compact always-on decision trails for AI debugging.

MVP keeps an in-memory ring buffer. Hot path is fire-and-forget (no sync DB I/O).
Join existing AgentReasoning / TradeJournal via signal_id; do not duplicate journals.
"""

from __future__ import annotations

import json
import uuid
from collections import deque
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Literal, Optional

from src.config import settings
from src.services.agent_log_service import agent_logger

# Correlated ids for the current scan / pair / signal (asyncio-safe).
_SCAN_ID: ContextVar[Optional[str]] = ContextVar("decision_scan_id", default=None)
_PAIR_ID: ContextVar[Optional[str]] = ContextVar("decision_pair_id", default=None)
_SIGNAL_ID: ContextVar[Optional[str]] = ContextVar("decision_signal_id", default=None)

DecisionLevel = Literal["compact", "verbose"]
DecisionOutcome = Literal["skip", "veto", "execute", "continue", "anomaly"]

# High-frequency / low-signal reasons omitted in compact mode.
_COMPACT_OMIT_REASONS = frozenset(
    {
        "below_entry_threshold",
        "beyond_stop_threshold",
        "market_closed",
        "not_scanned",
    }
)

# Reasons that trigger promote + anomaly tagging.
_ANOMALY_REASONS = frozenset(
    {
        "exception",
        "orchestrator_timeout",
        "kalman_state_invalid",
        "kalman_unavailable",
        "price_sanity_invalid",
        "stale_price_snapshot",
        "execution_blocked",
        "sizing_below_minimum",
    }
)

_SENSITIVE_KEY_FRAGMENTS = ("api_key", "token", "secret", "password", "key")


@dataclass
class DecisionEvent:
    """Compact decision breadcrumb at a typed branch point."""

    ts: str
    level: DecisionLevel
    scan_id: Optional[str]
    pair_id: Optional[str]
    signal_id: Optional[str]
    stage: str
    outcome: DecisionOutcome
    reason: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    path: List[str] = field(default_factory=list)
    promoted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def scrub_value(value: Any) -> Any:
    """Recursively scrub sensitive keys (same family as agent_log_service)."""
    if isinstance(value, dict):
        scrubbed: Dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if any(fragment in key_str.lower() for fragment in _SENSITIVE_KEY_FRAGMENTS):
                scrubbed[key_str] = "[REDACTED]"
            else:
                scrubbed[key_str] = scrub_value(item)
        return scrubbed
    if isinstance(value, list):
        return [scrub_value(item) for item in value]
    if isinstance(value, tuple):
        return [scrub_value(item) for item in value]
    return value


def truncate_inputs(value: Any, max_chars: int) -> Any:
    """Bound serialized size of nested inputs for ring storage."""
    if max_chars <= 0:
        return {}
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            out[str(key)] = truncate_inputs(item, max_chars)
        encoded = json.dumps(out, default=str, sort_keys=True)
        if len(encoded) <= max_chars:
            return out
        return {"_truncated": encoded[:max_chars] + "…"}
    if isinstance(value, list):
        trimmed = [truncate_inputs(item, max_chars) for item in value[:20]]
        if len(value) > 20:
            trimmed.append({"_omitted": len(value) - 20})
        return trimmed
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + "…"
    return value


class DecisionRecorder:
    """In-memory decision trail with promote + incident-pack export."""

    def __init__(
        self,
        maxsize: Optional[int] = None,
        input_max_chars: Optional[int] = None,
    ) -> None:
        self._maxsize = int(maxsize if maxsize is not None else settings.DECISION_TRACE_RING_SIZE)
        self._input_max_chars = int(
            input_max_chars if input_max_chars is not None else settings.DECISION_TRACE_INPUT_MAX_CHARS
        )
        self._events: Deque[DecisionEvent] = deque(maxlen=max(1, self._maxsize))
        self._last_anomaly_index: Optional[int] = None
        self._seq = 0

    # --- contextvars helpers -------------------------------------------------

    def begin_scan(self, scan_id: Optional[str] = None) -> str:
        """Start a scan correlation id and clear pair/signal context."""
        sid = scan_id or f"scan-{uuid.uuid4().hex[:12]}"
        _SCAN_ID.set(sid)
        _PAIR_ID.set(None)
        _SIGNAL_ID.set(None)
        return sid

    def set_pair_id(self, pair_id: Optional[str]) -> None:
        _PAIR_ID.set(pair_id)

    def set_signal_id(self, signal_id: Optional[str]) -> None:
        _SIGNAL_ID.set(signal_id)

    def clear_context(self) -> None:
        _SCAN_ID.set(None)
        _PAIR_ID.set(None)
        _SIGNAL_ID.set(None)

    @property
    def scan_id(self) -> Optional[str]:
        return _SCAN_ID.get()

    @property
    def pair_id(self) -> Optional[str]:
        return _PAIR_ID.get()

    @property
    def signal_id(self) -> Optional[str]:
        return _SIGNAL_ID.get()

    # --- core API ------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return str(settings.DECISION_TRACE_LEVEL).lower() != "off"

    @property
    def verbose(self) -> bool:
        return str(settings.DECISION_TRACE_LEVEL).lower() == "verbose"

    def record(
        self,
        *,
        stage: str,
        outcome: DecisionOutcome,
        reason: str,
        inputs: Optional[Dict[str, Any]] = None,
        pair_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        scan_id: Optional[str] = None,
        promote: Optional[bool] = None,
    ) -> Optional[DecisionEvent]:
        """Append a DecisionEvent. Never raises into the hot path."""
        try:
            if not self.enabled:
                return None

            reason_key = str(reason or "")
            if not self.verbose and reason_key in _COMPACT_OMIT_REASONS and outcome == "skip":
                return None

            is_anomaly = outcome == "anomaly" or reason_key in _ANOMALY_REASONS
            effective_outcome: DecisionOutcome = "anomaly" if is_anomaly else outcome

            level: DecisionLevel = "verbose" if (self.verbose or is_anomaly) else "compact"
            clean_inputs = truncate_inputs(scrub_value(inputs or {}), self._input_max_chars)

            path_str = ""
            try:
                path_str = agent_logger.get_path() or ""
            except Exception:
                path_str = ""
            path = [part for part in path_str.split(" -> ") if part] if path_str else []

            event = DecisionEvent(
                ts=_utc_now_iso(),
                level=level,
                scan_id=scan_id if scan_id is not None else self.scan_id,
                pair_id=pair_id if pair_id is not None else self.pair_id,
                signal_id=signal_id if signal_id is not None else self.signal_id,
                stage=stage,
                outcome=effective_outcome,
                reason=reason_key,
                inputs=clean_inputs if isinstance(clean_inputs, dict) else {"_value": clean_inputs},
                path=path,
                promoted=False,
            )
            self._events.append(event)
            self._seq += 1

            should_promote = promote if promote is not None else is_anomaly
            if should_promote:
                self.promote(around=event, radius=25)

            return event
        except Exception:
            return None

    def promote(self, *, around: Optional[DecisionEvent] = None, radius: int = 25) -> int:
        """Mark nearby events as promoted (retained for anomaly export)."""
        if not self._events:
            return 0
        events = list(self._events)
        center = len(events) - 1
        if around is not None:
            for idx, event in enumerate(events):
                if event is around or (
                    event.ts == around.ts
                    and event.reason == around.reason
                    and event.pair_id == around.pair_id
                    and event.signal_id == around.signal_id
                ):
                    center = idx
                    break
        start = max(0, center - radius)
        end = min(len(events), center + radius + 1)
        promoted = 0
        for event in events[start:end]:
            if not event.promoted:
                event.promoted = True
                promoted += 1
        self._last_anomaly_index = center
        # Rewrite deque preserving maxlen / order.
        self._events = deque(events, maxlen=max(1, self._maxsize))
        return promoted

    def events(self) -> List[DecisionEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()
        self._last_anomaly_index = None

    def filter_events(
        self,
        *,
        signal_id: Optional[str] = None,
        scan_id: Optional[str] = None,
        pair_id: Optional[str] = None,
        promoted_only: bool = False,
        last_anomaly: bool = False,
        radius: int = 50,
    ) -> List[DecisionEvent]:
        events = list(self._events)
        if last_anomaly:
            anomaly_idxs = [i for i, e in enumerate(events) if e.outcome == "anomaly" or e.promoted]
            if not anomaly_idxs:
                return []
            center = anomaly_idxs[-1]
            start = max(0, center - radius)
            end = min(len(events), center + radius + 1)
            return events[start:end]

        filtered: List[DecisionEvent] = []
        for event in events:
            if signal_id and event.signal_id != signal_id:
                continue
            if scan_id and event.scan_id != scan_id:
                continue
            if pair_id and event.pair_id != pair_id:
                continue
            if promoted_only and not event.promoted:
                continue
            filtered.append(event)
        return filtered

    def export_pack(
        self,
        *,
        out_dir: Path | str,
        signal_id: Optional[str] = None,
        scan_id: Optional[str] = None,
        pair_id: Optional[str] = None,
        last_anomaly: bool = False,
        journal_refs: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Write an incident pack directory. Returns the pack path."""
        selected = self.filter_events(
            signal_id=signal_id,
            scan_id=scan_id,
            pair_id=pair_id,
            last_anomaly=last_anomaly,
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        label = signal_id or scan_id or ("last-anomaly" if last_anomaly else "trail")
        safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)[:80]
        pack_dir = Path(out_dir) / f"{stamp}_{safe_label}"
        pack_dir.mkdir(parents=True, exist_ok=True)

        trail_path = pack_dir / "trail.jsonl"
        with trail_path.open("w", encoding="utf-8") as fh:
            for event in selected:
                fh.write(json.dumps(event.to_dict(), default=str, sort_keys=True) + "\n")

        outcomes: Dict[str, int] = {}
        reasons: Dict[str, int] = {}
        for event in selected:
            outcomes[event.outcome] = outcomes.get(event.outcome, 0) + 1
            reasons[event.reason] = reasons.get(event.reason, 0) + 1

        manifest = {
            "created_at": _utc_now_iso(),
            "filter": {
                "signal_id": signal_id,
                "scan_id": scan_id,
                "pair_id": pair_id,
                "last_anomaly": last_anomaly,
            },
            "event_count": len(selected),
            "outcomes": outcomes,
            "top_reasons": dict(sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))[:20]),
            "decision_trace_level": settings.DECISION_TRACE_LEVEL,
            "ring_size": self._maxsize,
            "ring_occupancy": len(self._events),
            "journal_refs": scrub_value(journal_refs or {}),
        }
        (pack_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        summary_lines = [
            "# Decision Flight Recorder — Incident Summary",
            "",
            f"- Created: `{manifest['created_at']}`",
            f"- Events: **{len(selected)}**",
            f"- Filter: signal_id=`{signal_id}` scan_id=`{scan_id}` pair_id=`{pair_id}` last_anomaly=`{last_anomaly}`",
            "",
            "## Outcomes",
        ]
        for key, count in sorted(outcomes.items()):
            summary_lines.append(f"- `{key}`: {count}")
        summary_lines.extend(["", "## Top reasons"])
        for key, count in list(manifest["top_reasons"].items())[:10]:
            summary_lines.append(f"- `{key}`: {count}")
        if selected:
            summary_lines.extend(
                [
                    "",
                    "## First / last event",
                    f"- First: `{selected[0].ts}` stage=`{selected[0].stage}` reason=`{selected[0].reason}`",
                    f"- Last: `{selected[-1].ts}` stage=`{selected[-1].stage}` reason=`{selected[-1].reason}`",
                ]
            )
        (pack_dir / "summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

        hint = """# AGENT_HINT — Decision Flight Recorder

## How to read this pack

1. Start with `summary.md` for outcome / reason histograms.
2. Walk `trail.jsonl` chronologically — each line is one `DecisionEvent` at a typed branch point.
3. Correlate with existing journals via `signal_id` (do **not** expect duplicated thought journals here):
   - `AgentReasoning.trace_id` == `signal_id` (UUID written by `audit_service.log_thought_process`)
   - `TradeJournal.signal_id` == `signal_id`
   - Shadow / live ledger rows also carry `signal_id`

## Suggested investigation prompts

- Which stage last returned before execute? (`stage` + `outcome` + `reason`)
- Was this an anomaly promote window? (`promoted=true` / `outcome=anomaly`)
- For the same `scan_id`, which other pairs skipped and why?

## Config

- `DECISION_TRACE_LEVEL=compact|verbose|off` (default compact)
- Compact mode omits routine skips: below_entry_threshold, beyond_stop_threshold, market_closed, not_scanned
"""
        (pack_dir / "AGENT_HINT.md").write_text(hint, encoding="utf-8")
        return pack_dir


decision_recorder = DecisionRecorder()


def reset_decision_recorder_for_tests(
    *,
    maxsize: int = 100,
    input_max_chars: int = 500,
) -> DecisionRecorder:
    """Replace the module singleton for isolated unit tests."""
    global decision_recorder
    decision_recorder = DecisionRecorder(maxsize=maxsize, input_max_chars=input_max_chars)
    decision_recorder.clear_context()
    return decision_recorder
