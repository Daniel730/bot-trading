"""Limited-LIVE operational kill criteria (Phase-5).

Separate from capital halt / LIVE readiness — these are *operator policy*
thresholds for stopping limited live once it has started.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.config import settings

logger = logging.getLogger(__name__)


async def evaluate_limited_live_kill(
    *,
    persistence_service: Any,
    divergence_count: Optional[int] = None,
) -> dict[str, Any]:
    """Return ``{kill: bool, reason, details}``.

    Defaults (overridable via settings attrs if present):
    - max consecutive reconcile failures: 3
    - max shadow/live divergences (session): 10
    - max daily loss already covered by capital_halt
    """
    details: dict[str, Any] = {}
    max_reconcile_fails = int(
        getattr(settings, "LIMITED_LIVE_MAX_RECONCILE_FAILS", 3) or 3
    )
    max_divergences = int(
        getattr(settings, "LIMITED_LIVE_MAX_DIVERGENCES", 10) or 10
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
            "reason": "reconcile_failures_exceeded",
            "details": details,
        }

    if divergence_count is None:
        try:
            from src.services.shadow_live_divergence import shadow_live_divergence_monitor

            divergence_count = shadow_live_divergence_monitor.divergence_count()
        except Exception:  # noqa: BLE001
            divergence_count = 0
    details["divergence_count"] = int(divergence_count or 0)
    if int(divergence_count or 0) >= max_divergences:
        return {
            "kill": True,
            "reason": "shadow_live_divergences_exceeded",
            "details": details,
        }

    return {"kill": False, "reason": None, "details": details}


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
