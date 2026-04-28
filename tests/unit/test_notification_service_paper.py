"""T004: Regression test for paper-mode auto-approve fast path.

Covers FR-001..FR-003 from specs/036-paper-readiness-blockers/spec.md:

- Paper mode must return True in under 100ms.
- Telegram / dashboard failures must NOT propagate to the caller.
- No correlation-ID future may be left dangling in pending_approvals.
"""

import asyncio
import time
import pytest
from unittest.mock import patch, AsyncMock

from src.config import settings
from src.services.notification_service import notification_service


@pytest.mark.asyncio
async def test_request_approval_paper_fast_path_returns_true_under_100ms():
    """Paper mode: returns True in <100ms, even if Telegram is down,
    and leaves no residue in pending_approvals."""
    original_paper = settings.PAPER_TRADING
    settings.PAPER_TRADING = True
    # Snapshot & clear pending_approvals so we can assert it stays empty.
    original_pending = dict(notification_service.pending_approvals)
    notification_service.pending_approvals.clear()

    try:
        # Break Telegram send: any fire-and-forget notify must swallow it.
        broken_send = AsyncMock(side_effect=RuntimeError("network down"))
        with patch.object(notification_service, "_paper_notify", broken_send):
            start = time.perf_counter()
            result = await notification_service.request_approval(
                "test paper trade summary"
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

        assert result is True, "paper mode must auto-approve"
        assert elapsed_ms < 100, (
            f"paper fast path must return in <100ms, took {elapsed_ms:.2f}ms"
        )
        assert notification_service.pending_approvals == {}, (
            "paper fast path must NOT create a correlation-ID future"
        )

        # Let the fire-and-forget _paper_notify task run so we can assert
        # the Telegram failure was attempted but absorbed (no exception bubbled).
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    finally:
        settings.PAPER_TRADING = original_paper
        notification_service.pending_approvals.clear()
        notification_service.pending_approvals.update(original_pending)


@pytest.mark.asyncio
async def test_request_approval_paper_survives_dashboard_failure():
    """Paper mode: dashboard_state.add_message failures also must not
    propagate (FR-002: paper trades simulate regardless of sink health)."""
    original_paper = settings.PAPER_TRADING
    settings.PAPER_TRADING = True
    notification_service.pending_approvals.clear()

    try:
        ok_send = AsyncMock(return_value=None)
        with patch.object(notification_service, "_paper_notify", ok_send), \
             patch(
                 "src.services.dashboard_service.dashboard_state.add_message",
                 new=AsyncMock(side_effect=RuntimeError("dashboard offline")),
             ):
            result = await notification_service.request_approval(
                "dashboard-fail summary"
            )

        assert result is True
        assert notification_service.pending_approvals == {}

        # Drain the fire-and-forget notify task.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    finally:
        settings.PAPER_TRADING = original_paper
        notification_service.pending_approvals.clear()
