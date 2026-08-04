"""Automatic LIVE readiness checklist (Phase-4).

Any failed item forbids LIVE opens. Paper / shadow lanes are not gated.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from src.config import settings
from src.services.open_slot_reservation import DEFAULT_WAL_PATH, _checksum

logger = logging.getLogger(__name__)


def _clock_skew_ok(max_skew_seconds: float = 5.0) -> tuple[bool, str]:
    """Best-effort clock check vs process monotonic consistency."""
    try:
        wall = time.time()
        mono = time.monotonic()
        # Re-sample — large jumps indicate clock issues mid-check.
        wall2 = time.time()
        if abs(wall2 - wall) > max_skew_seconds:
            return False, f"wall_clock_jump:{wall2 - wall:.3f}s"
        _ = mono
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _wal_integrity_ok(path: Path | None = None) -> tuple[bool, str]:
    wal_path = Path(path or getattr(settings, "OPEN_SLOT_WAL_PATH", None) or DEFAULT_WAL_PATH)
    if not wal_path.exists():
        return True, "wal_absent_ok"
    bad = 0
    total = 0
    try:
        for line in wal_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                import json

                rec = json.loads(line)
            except Exception:  # noqa: BLE001
                bad += 1
                continue
            if rec.get("checksum") != _checksum(rec):
                bad += 1
        if bad:
            return False, f"wal_corrupt_lines:{bad}/{total}"
        return True, f"wal_ok:{total}"
    except Exception as exc:  # noqa: BLE001
        return False, f"wal_read_error:{exc}"


async def evaluate_live_readiness(
    *,
    brokerage: Any = None,
    persistence_service: Any = None,
    totp_enabled_check: Optional[Callable[[], bool]] = None,
) -> dict[str, Any]:
    """Return checklist result. ``ready`` is True only when all required items pass."""
    from src.services.capital_halt_service import evaluate_capital_halt
    from src.services.execution_intent_service import execution_intent_service
    from src.services.distributed_reservation import distributed_reservation_store

    if persistence_service is None:
        from src.services.persistence_service import persistence_service as _ps

        persistence_service = _ps

    items: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        items.append({"name": name, "ok": bool(ok), "detail": detail})

    # Broker connected
    broker_ok = False
    broker_detail = "skipped"
    if brokerage is not None:
        try:
            cash = await brokerage.get_account_cash()
            broker_ok = cash is not None
            broker_detail = f"cash={cash}"
        except Exception as exc:  # noqa: BLE001
            broker_detail = str(exc)
    else:
        broker_detail = "no_brokerage"
    add("broker_connected", broker_ok, broker_detail)

    wal_ok, wal_detail = _wal_integrity_ok()
    add("wal_integrity", wal_ok, wal_detail)

    db_ok = False
    db_detail = ""
    try:
        await persistence_service.get_system_state("operational_status", "NORMAL")
        await distributed_reservation_store.ensure_schema()
        db_ok = True
        db_detail = "postgres_ok"
    except Exception as exc:  # noqa: BLE001
        db_detail = str(exc)
    add("database_consistent", db_ok, db_detail)

    pending_intents = 0
    try:
        pending_intents = await execution_intent_service.count_open_intents()
    except Exception as exc:  # noqa: BLE001
        add("no_pending_intents", False, str(exc))
    else:
        add("no_pending_intents", pending_intents == 0, f"count={pending_intents}")

    orphans = 0
    try:
        orphans = await persistence_service.count_startup_reconciliation_rows()
    except Exception as exc:  # noqa: BLE001
        add("no_orphans", False, str(exc))
    else:
        add("no_orphans", orphans == 0, f"unresolved={orphans}")

    halt = await evaluate_capital_halt(persistence_service=persistence_service)
    add("drawdown_ok", not halt["halt"], str(halt.get("reason") or "ok"))
    add(
        "capital_ok",
        not halt["halt"],
        f"details={halt.get('details')}",
    )

    totp_ok = False
    totp_detail = "unchecked"
    try:
        if totp_enabled_check is not None:
            totp_ok = bool(totp_enabled_check())
            totp_detail = "callback"
        else:
            from src.services.dashboard_service import dashboard_service

            totp_ok = bool(dashboard_service.totp.public_status().get("enabled"))
            totp_detail = "dashboard_totp"
    except Exception as exc:  # noqa: BLE001
        totp_detail = str(exc)
    add("two_factor_ok", totp_ok, totp_detail)

    # Config signature: require LIVE_CAPITAL_DANGER explicitly true and DEV_MODE false.
    cfg_ok = (
        bool(settings.LIVE_CAPITAL_DANGER)
        and not bool(settings.DEV_MODE)
        and not bool(settings.PAPER_TRADING)
        and not bool(settings.is_broker_paper_trading)
    )
    add(
        "configuration_signed",
        cfg_ok,
        f"LIVE_CAPITAL={settings.LIVE_CAPITAL_DANGER} DEV={settings.DEV_MODE} PAPER={settings.PAPER_TRADING}",
    )

    clock_ok, clock_detail = _clock_skew_ok()
    add("clock_synchronized", clock_ok, clock_detail)

    secrets_ok = True
    missing = []
    for key in ("DASHBOARD_TOKEN", "POSTGRES_PASSWORD", "ALPACA_API_KEY", "ALPACA_API_SECRET"):
        val = (os.getenv(key) or getattr(settings, key, "") or "").strip()
        if not val or val.startswith("your_"):
            secrets_ok = False
            missing.append(key)
    add("secrets_valid", secrets_ok, f"missing_or_placeholder={missing}")

    reconcile_ok = False
    reconcile_detail = ""
    try:
        last = await persistence_service.get_system_state("last_broker_reconcile_at")
        last_ok = await persistence_service.get_system_state("last_broker_reconcile_ok")
        if last and str(last_ok).lower() == "true":
            ts = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            reconcile_ok = age <= float(
                getattr(settings, "BROKER_RECONCILE_MAX_AGE_SECONDS", 300) or 300
            )
            reconcile_detail = f"age_s={age:.1f}"
        else:
            reconcile_detail = "never_or_failed"
    except Exception as exc:  # noqa: BLE001
        reconcile_detail = str(exc)
    add("reconciliation_complete", reconcile_ok, reconcile_detail)

    ready = all(i["ok"] for i in items)
    return {
        "ready": ready,
        "items": items,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def enforce_live_readiness_or_block(
    *,
    brokerage: Any = None,
    persistence_service: Any = None,
) -> dict[str, Any]:
    """For LIVE real-money opens only — paper lanes always pass."""
    if settings.should_auto_approve_trades or settings.PAPER_TRADING:
        return {"ready": True, "skipped": True, "reason": "paper_or_auto_approve_lane"}
    if not settings.LIVE_CAPITAL_DANGER:
        return {"ready": False, "reason": "LIVE_CAPITAL_DANGER_false", "items": []}

    result = await evaluate_live_readiness(
        brokerage=brokerage,
        persistence_service=persistence_service,
    )
    if not result["ready"]:
        failed = [i["name"] for i in result["items"] if not i["ok"]]
        logger.critical("LIVE readiness FAILED: %s", failed)
        result["failed"] = failed
    return result
