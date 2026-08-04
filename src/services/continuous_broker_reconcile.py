"""Continuous broker reconciliation — broker is source of truth (Phase-4)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.config import settings

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 60.0


async def run_broker_reconciliation_cycle(
    *,
    brokerage,
    persistence_service: Any,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Pull broker state and repair local divergence.

    Local ledger is never treated as absolute truth. Order of operations:
    1. Broker-confirmed closes
    2. Broker-confirmed pair restores
    3. Flat orphan ledger closes
    4. Leg-A orphan emergency flatten
    5. Persist last reconcile timestamp
    """
    summary: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "broker_ok": True,
    }
    try:
        from src.services.ledger_reconcile_service import (
            auto_close_flat_orphans,
            auto_reconcile_broker_confirmed_closes,
            auto_reconcile_broker_confirmed_pairs,
            plan_signal_level_reconciliation,
            log_signal_reconciliation_plans,
        )
        from src.services.leg_orphan_recovery import recover_leg_a_orphans

        summary["closes"] = await auto_reconcile_broker_confirmed_closes(
            brokerage=brokerage, dry_run=dry_run
        )
        if settings.auto_reconcile_broker_confirmed_pairs:
            summary["pairs"] = await auto_reconcile_broker_confirmed_pairs(
                brokerage=brokerage, dry_run=dry_run
            )
        if settings.auto_reconcile_flat_orphans:
            summary["flat_orphans"] = await auto_close_flat_orphans(
                brokerage=brokerage, dry_run=dry_run
            )
        summary["leg_orphans"] = await recover_leg_a_orphans(
            brokerage=brokerage, dry_run=dry_run
        )
        try:
            plans = await plan_signal_level_reconciliation(brokerage=brokerage)
            log_signal_reconciliation_plans(plans)
            summary["plans"] = {
                "count": len(plans.get("plans") or [])
                if isinstance(plans, dict)
                else 0
            }
        except Exception as exc:  # noqa: BLE001
            logger.debug("reconcile plan audit failed: %s", exc)

        await persistence_service.set_system_state(
            "last_broker_reconcile_at",
            datetime.now(timezone.utc).isoformat(),
        )
        await persistence_service.set_system_state(
            "last_broker_reconcile_ok",
            "true",
        )
    except Exception as exc:  # noqa: BLE001
        summary["broker_ok"] = False
        summary["error"] = str(exc)
        logger.error("broker reconciliation cycle failed: %s", exc)
        try:
            await persistence_service.set_system_state(
                "last_broker_reconcile_ok", "false"
            )
        except Exception:  # noqa: BLE001
            pass
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    return summary


class ContinuousBrokerReconciler:
    def __init__(self, *, interval_seconds: float = DEFAULT_INTERVAL_SECONDS):
        self.interval_seconds = float(
            getattr(settings, "BROKER_RECONCILE_INTERVAL_SECONDS", None)
            or interval_seconds
        )
        self._task = None

    async def loop(self, monitor) -> None:
        import asyncio

        from src.services.persistence_service import persistence_service

        while True:
            try:
                await run_broker_reconciliation_cycle(
                    brokerage=monitor.brokerage,
                    persistence_service=persistence_service,
                    dry_run=False,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("ContinuousBrokerReconciler: %s", exc)
            await asyncio.sleep(self.interval_seconds)


continuous_broker_reconciler = ContinuousBrokerReconciler()
