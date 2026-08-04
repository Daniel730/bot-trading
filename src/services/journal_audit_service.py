"""TradeJournal vs TradeLedger continuity audit / repair.

Keeps signal_id joins healthy after closes and reconcile auto-closes:
- CLOSED ledger rows must have a TradeJournal row
- that journal should carry exit_reason when ledger metadata does
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from sqlalchemy import select

from src.services.persistence_service import (
    ExitReason,
    OrderStatus,
    TradeJournal,
    TradeLedger,
    persistence_service,
)

logger = logging.getLogger(__name__)


def _as_uuid(value: Any) -> Optional[uuid.UUID]:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _exit_reason_from_ledger_meta(meta: Any) -> Optional[ExitReason]:
    if not isinstance(meta, dict):
        return None
    raw = meta.get("exit_reason")
    if raw is None:
        return None
    try:
        return ExitReason(str(raw))
    except ValueError:
        return None


def classify_journal_ledger_gap(
    *,
    signal_id: uuid.UUID,
    journal: Optional[TradeJournal],
    ledger_exit_reason: Optional[ExitReason],
) -> Optional[str]:
    """Return a gap code or None when the journal is continuous with the close."""
    if journal is None:
        return "missing_journal"
    if journal.exit_reason is None and ledger_exit_reason is not None:
        return "missing_exit_reason"
    if journal.exit_reason is None:
        return "missing_exit_reason_no_ledger_hint"
    return None


async def audit_journal_vs_ledger(*, repair: bool = False) -> dict[str, Any]:
    """Scan CLOSED ledger signals for missing / incomplete TradeJournal rows.

    When repair=True, upserts exit_reason (from ledger metadata, else MANUAL).
    Paper-safe: never touches broker state or open ledger rows.
    """
    missing_journal: list[str] = []
    missing_exit_reason: list[str] = []
    missing_exit_reason_no_hint: list[str] = []
    repaired = 0

    async with persistence_service.AsyncSessionLocal() as session:
        ledger_rows = (
            await session.execute(
                select(TradeLedger.signal_id, TradeLedger.metadata_json).where(
                    TradeLedger.status == OrderStatus.CLOSED,
                    TradeLedger.signal_id.is_not(None),
                )
            )
        ).all()

        by_signal: dict[uuid.UUID, Optional[ExitReason]] = {}
        for signal_id_raw, meta in ledger_rows:
            signal_id = _as_uuid(signal_id_raw)
            if signal_id is None:
                continue
            reason = _exit_reason_from_ledger_meta(meta)
            # Prefer an explicit reason if any leg carries one.
            if signal_id not in by_signal or (reason is not None and by_signal[signal_id] is None):
                by_signal[signal_id] = reason

        if not by_signal:
            return {
                "examined_signals": 0,
                "missing_journal": [],
                "missing_exit_reason": [],
                "missing_exit_reason_no_hint": [],
                "repaired": 0,
                "repair": repair,
            }

        journals = (
            await session.execute(
                select(TradeJournal).where(TradeJournal.signal_id.in_(list(by_signal.keys())))
            )
        ).scalars().all()
        journal_by_signal = {j.signal_id: j for j in journals if j.signal_id is not None}

        for signal_id, ledger_reason in by_signal.items():
            gap = classify_journal_ledger_gap(
                signal_id=signal_id,
                journal=journal_by_signal.get(signal_id),
                ledger_exit_reason=ledger_reason,
            )
            if gap is None:
                continue
            sid = str(signal_id)
            if gap == "missing_journal":
                missing_journal.append(sid)
            elif gap == "missing_exit_reason":
                missing_exit_reason.append(sid)
            else:
                missing_exit_reason_no_hint.append(sid)

            if not repair:
                continue

            # Prefer ledger-stamped reason; MANUAL for reconcile-only closes.
            reason = ledger_reason or ExitReason.MANUAL
            await persistence_service.ensure_journal_exit_reason(
                signal_id,
                reason,
                session=session,
            )
            repaired += 1

        if repair and repaired:
            await session.commit()

    summary = {
        "examined_signals": len(by_signal),
        "missing_journal": missing_journal,
        "missing_exit_reason": missing_exit_reason,
        "missing_exit_reason_no_hint": missing_exit_reason_no_hint,
        "gap_count": (
            len(missing_journal)
            + len(missing_exit_reason)
            + len(missing_exit_reason_no_hint)
        ),
        "repaired": repaired,
        "repair": repair,
    }
    if summary["gap_count"]:
        logger.warning(
            "Journal/ledger audit: examined=%s gaps=%s missing_journal=%s "
            "missing_exit_reason=%s no_hint=%s repaired=%s",
            summary["examined_signals"],
            summary["gap_count"],
            len(missing_journal),
            len(missing_exit_reason),
            len(missing_exit_reason_no_hint),
            repaired,
        )
    else:
        logger.info(
            "Journal/ledger audit: examined=%s gaps=0",
            summary["examined_signals"],
        )
    return summary
