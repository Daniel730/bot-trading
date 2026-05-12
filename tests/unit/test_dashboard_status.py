from unittest.mock import AsyncMock

import pytest

from src.services.dashboard_service import dashboard_service, dashboard_state


@pytest.mark.asyncio
async def test_summary_reports_manual_review_after_startup_fail_fast(monkeypatch):
    monkeypatch.setattr(dashboard_state, "desired_bot_state", "RUNNING")
    monkeypatch.setattr(dashboard_state, "stage", "Monitoring")
    monkeypatch.setattr(dashboard_state, "active_signals", [])
    monkeypatch.setattr(
        dashboard_service,
        "latest_health",
        lambda: {"uptime_seconds": 12, "cpu_pct": 1.0, "system_memory_pct": 2.0},
    )

    monkeypatch.setattr(
        "src.services.persistence_service.persistence_service.get_system_state",
        AsyncMock(return_value="PAUSED_REQUIRES_MANUAL_REVIEW"),
    )
    monkeypatch.setattr(
        "src.services.persistence_service.persistence_service.get_trade_summary",
        AsyncMock(return_value={"win_rate": 0.0, "wins": 0, "losses": 0, "closed_trades": 0}),
    )
    monkeypatch.setattr(
        "src.services.persistence_service.persistence_service.get_trade_history",
        AsyncMock(return_value={"items": []}),
    )
    monkeypatch.setattr(
        "src.services.persistence_service.persistence_service.get_open_signals",
        AsyncMock(return_value=[]),
    )

    summary = await dashboard_service.build_summary()

    assert summary["desired_bot_state"] == "RUNNING"
    assert summary["operational_status"] == "PAUSED_REQUIRES_MANUAL_REVIEW"
    assert summary["bot_status"] == "PAUSED_REQUIRES_MANUAL_REVIEW"
    assert summary["blocked"] is True
