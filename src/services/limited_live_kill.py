"""Limited-LIVE operational kill criteria (severity-aware).

Policy:
  - Reconcile consecutive failures → block new entries (CRITICAL equivalent)
  - Any FATAL divergence → kill + recommend flatten
  - Any CRITICAL divergence → kill (block new entries only)
  - INFO / WARNING piles do **not** stop the bot by themselves
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.config import settings

logger = logging.getLogger(__name__)


async def evaluate_limited_live_kill(
    *,
    persistence_service: Any,
    divergence_count: Optional[int] = None,  # retained for back-compat; unused for policy
) -> dict[str, Any]:
    """Return ``{kill, flatten_recommended, reason, details, severity}``."""
    details: dict[str, Any] = {}
    max_reconcile_fails = int(
        getattr(settings, "LIMITED_LIVE_MAX_RECONCILE_FAILS", 3) or 3
    )

    try:
        fails = int(
            await persistence_service.get_system_state(
                "broker_reconcile_consecutive_fails", "0"
            )
            or 0
        )
    except Exception:  # noqa: BLE001
        fails = 0
    details["reconcile_consecutive_fails"] = fails
    if fails >= max_reconcile_fails:
        return {
            "kill": True,
            "flatten_recommended": False,
            "severity": "CRITICAL",
            "reason": "reconcile_failures_exceeded",
            "details": details,
        }

    counts: dict[str, int] = {}
    highest = None
    try:
        from src.services.shadow_live_divergence import shadow_live_divergence_monitor

        counts = shadow_live_divergence_monitor.severity_counts()
        highest = shadow_live_divergence_monitor.highest_severity()
    except Exception:  # noqa: BLE001
        counts = {}
    details["divergence_severity_counts"] = counts
    details["highest_divergence_severity"] = highest
    # Legacy field for dashboards that still read a scalar.
    details["divergence_count"] = int(divergence_count) if divergence_count is not None else sum(
        counts.values()
    )

    if counts.get("FATAL", 0) > 0:
        return {
            "kill": True,
            "flatten_recommended": True,
            "severity": "FATAL",
            "reason": "fatal_shadow_live_divergence",
            "details": details,
        }
    if counts.get("CRITICAL", 0) > 0:
        return {
            "kill": True,
            "flatten_recommended": False,
            "severity": "CRITICAL",
            "reason": "critical_shadow_live_divergence",
            "details": details,
        }

    return {
        "kill": False,
        "flatten_recommended": False,
        "severity": highest,
        "reason": None,
        "details": details,
    }


async def note_reconcile_result(persistence_service: Any, *, ok: bool) -> None:
    key = "broker_reconcile_consecutive_fails"
    try:
        if ok:
            await persistence_service.set_system_state(key, "0")
        else:
            cur = int(await persistence_service.get_system_state(key, "0") or 0)
            await persistence_service.set_system_state(key, str(cur + 1))
    except Exception as exc:  # noqa: BLE001
        logger.warning("limited_live_kill: could not update reconcile fail counter: %s", exc)
