"""Regression tests for adversarial audit remediations (2026-08-04)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src import mcp_server
from src.config import Settings, settings
from src.services.capital_halt_service import (
    evaluate_capital_halt,
    enforce_capital_halt_or_raise_state,
)
from src.services.execution_lane import close_uses_broker
from src.services.notification_service import notification_service
from tests.unit.test_mcp_execute_trade_safety import _call_mcp_tool


@pytest.mark.asyncio
async def test_f001_live_below_threshold_never_auto_approves_with_telegram():
    """F-001: LIVE + Telegram + force_manual=False must not short-circuit on threshold."""
    originals = {
        "PAPER_TRADING": settings.PAPER_TRADING,
        "DEV_MODE": settings.DEV_MODE,
        "LIVE_CAPITAL_DANGER": settings.LIVE_CAPITAL_DANGER,
        "ALPACA_BASE_URL": settings.ALPACA_BASE_URL,
        "APPROVAL_THRESHOLD": settings.APPROVAL_THRESHOLD,
    }
    original_telegram = notification_service._telegram_enabled
    original_app = notification_service.app
    original_chat = notification_service.chat_id
    notification_service.pending_approvals.clear()
    notification_service.pending_approval_summaries.clear()

    try:
        settings.PAPER_TRADING = False
        settings.DEV_MODE = False
        settings.LIVE_CAPITAL_DANGER = True
        settings.ALPACA_BASE_URL = "https://api.alpaca.markets"
        settings.APPROVAL_THRESHOLD = 10_000.0
        notification_service._telegram_enabled = True
        notification_service.chat_id = "1"
        notification_service.app = SimpleNamespace(
            bot=SimpleNamespace(send_message=AsyncMock(return_value=None))
        )

        assert settings.should_auto_approve_trades is False

        async def _resolve_soon():
            await asyncio.sleep(0.05)
            cid = next(iter(notification_service.pending_approvals))
            notification_service.resolve_pending_approval(cid, approved=True)

        with patch(
            "src.services.dashboard_service.dashboard_state.add_message",
            new=AsyncMock(),
        ):
            resolver = asyncio.create_task(_resolve_soon())
            result = await notification_service.request_approval(
                "live pair below threshold",
                trade_value=1.0,
                force_manual=False,
            )
            await resolver

        assert result is True
        notification_service.app.bot.send_message.assert_awaited()
        assert notification_service.pending_approvals == {}
    finally:
        for key, value in originals.items():
            setattr(settings, key, value)
        notification_service._telegram_enabled = original_telegram
        notification_service.app = original_app
        notification_service.chat_id = original_chat
        notification_service.pending_approvals.clear()
        notification_service.pending_approval_summaries.clear()


def test_f003_validate_secrets_rejects_dev_mode_without_paper(monkeypatch):
    """F-003: DEV_MODE + PAPER_TRADING=false must fail closed at Settings load."""
    monkeypatch.setenv("PAPER_TRADING", "false")
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("LIVE_CAPITAL_DANGER", "true")
    monkeypatch.setenv("DASHBOARD_TOKEN", "unit-test-dashboard-token-not-default")
    monkeypatch.setenv("POSTGRES_PASSWORD", "unit-test-postgres-password-not-default")
    monkeypatch.setenv("DASHBOARD_ALLOWED_ORIGINS", "http://localhost:5173")
    with pytest.raises(ValueError, match="DEV_MODE=true requires PAPER_TRADING=true"):
        Settings(_env_file=None)


def test_f005_paper_endpoint_hostname_not_substring():
    """F-005: spoofed path/host must not count as Alpaca paper."""
    good = Settings.model_construct(ALPACA_BASE_URL="https://paper-api.alpaca.markets")
    assert good.is_alpaca_paper_endpoint is True

    spoof_path = Settings.model_construct(
        ALPACA_BASE_URL="https://evil.example/paper-api.alpaca.markets"
    )
    assert spoof_path.is_alpaca_paper_endpoint is False

    spoof_subdomain = Settings.model_construct(
        ALPACA_BASE_URL="https://paper-api.alpaca.markets.evil.example"
    )
    assert spoof_subdomain.is_alpaca_paper_endpoint is False

    live = Settings.model_construct(ALPACA_BASE_URL="https://api.alpaca.markets")
    assert live.is_alpaca_paper_endpoint is False


def test_f009_untagged_legacy_never_closes_via_broker():
    legacy = {"signal_id": "legacy", "legs": [{"ticker": "AAPL", "side": "BUY", "quantity": 1}]}
    assert close_uses_broker(legacy, paper_trading=True) is False
    assert close_uses_broker(legacy, paper_trading=False) is False


@pytest.mark.asyncio
async def test_f002_daily_loss_triggers_capital_halt(monkeypatch):
    monkeypatch.setattr(settings, "MAX_DRAWDOWN", 0.10)
    monkeypatch.setattr(settings, "ALPACA_BUDGET_USD", 10_000.0)

    persistence = SimpleNamespace(
        get_system_state=AsyncMock(return_value="NORMAL"),
        get_daily_pnl_for_date=AsyncMock(return_value=-1500.0),
        set_system_state=AsyncMock(),
    )
    result = await evaluate_capital_halt(
        persistence_service=persistence,
        performance_service=None,
    )
    assert result["halt"] is True
    assert result["reason"] == "daily_loss_exceeds_max_drawdown"

    notify = SimpleNamespace(send_message=AsyncMock())
    enforced = await enforce_capital_halt_or_raise_state(
        persistence_service=persistence,
        performance_service=None,
        notification_service=notify,
    )
    assert enforced["halt"] is True
    persistence.set_system_state.assert_awaited_once_with(
        "operational_status", "DAILY_LOSS_HALT"
    )
    notify.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_f002_operational_pause_blocks_opens():
    persistence = SimpleNamespace(
        get_system_state=AsyncMock(return_value="PAUSED"),
        get_daily_pnl_for_date=AsyncMock(return_value=0.0),
    )
    result = await evaluate_capital_halt(persistence_service=persistence)
    assert result["halt"] is True
    assert "PAUSED" in (result["reason"] or "")


def test_f008_mcp_rejects_when_token_unset_or_placeholder(monkeypatch):
    monkeypatch.delenv("MCP_TOOL_TOKEN", raising=False)
    denied = mcp_server._auth_rejection("")
    assert denied is not None
    assert denied["status"] == "rejected"
    assert "not configured" in denied["reason"]

    monkeypatch.setenv("MCP_TOOL_TOKEN", "changeme")
    denied2 = mcp_server._auth_rejection("changeme")
    assert denied2 is not None
    assert "not configured" in denied2["reason"]


@pytest.mark.asyncio
async def test_f008_mcp_market_data_requires_configured_token(monkeypatch):
    monkeypatch.delenv("MCP_TOOL_TOKEN", raising=False)
    get_price = AsyncMock(return_value=42.0)
    monkeypatch.setattr(mcp_server.redis_service, "get_price", get_price)
    result = json.loads(
        await _call_mcp_tool(mcp_server.get_market_data, tickers=["MSFT"], source="alpaca")
    )
    assert result["status"] == "rejected"
    assert "not configured" in result["reason"]
    get_price.assert_not_awaited()
