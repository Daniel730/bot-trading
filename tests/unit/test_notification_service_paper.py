"""T004: Regression test for paper-mode auto-approve fast path.

Covers FR-001..FR-003 from specs/036-paper-readiness-blockers/spec.md:

- Paper mode must return True in under 100ms.
- Telegram / dashboard failures must NOT propagate to the caller.
- No correlation-ID future may be left dangling in pending_approvals.
"""

import asyncio
import logging
import sys
import time
import pytest
from types import SimpleNamespace
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


@pytest.mark.asyncio
async def test_request_approval_paper_task_uses_scheduled_notify_callable():
    original_paper = settings.PAPER_TRADING
    original_enabled = notification_service._telegram_enabled
    original_app = notification_service.app
    settings.PAPER_TRADING = True
    notification_service.pending_approvals.clear()

    class FakeBot:
        async def send_message(self, **_kwargs):
            return None

    class FakeApp:
        bot = FakeBot()

    try:
        notification_service._telegram_enabled = True
        notification_service.app = FakeApp()
        fake_notify = AsyncMock(return_value=None)

        with patch.object(notification_service, "_paper_notify", fake_notify), \
             patch(
                 "src.services.dashboard_service.dashboard_state.add_message",
                 new=AsyncMock(),
             ):
            result = await notification_service.request_approval(
                "patched paper notification"
            )

        assert result is True
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        fake_notify.assert_awaited_once_with("patched paper notification")
    finally:
        settings.PAPER_TRADING = original_paper
        notification_service._telegram_enabled = original_enabled
        notification_service.app = original_app
        notification_service.pending_approvals.clear()


@pytest.mark.asyncio
async def test_paper_notify_logs_and_redacts_telegram_token_from_send_failure(caplog, capsys):
    original_enabled = notification_service._telegram_enabled
    original_app = notification_service.app
    original_token = notification_service.token
    leaked_token = "123456:SUPER_SECRET_TOKEN"
    leaked_url = f"https://api.telegram.org/bot{leaked_token}/sendMessage"

    class FailingBot:
        async def send_message(self, **_kwargs):
            raise RuntimeError(f"telegram failed: {leaked_url}")

    class FakeApp:
        bot = FailingBot()

    try:
        notification_service._telegram_enabled = True
        notification_service.app = FakeApp()
        notification_service.token = leaked_token

        with caplog.at_level(logging.WARNING, logger="src.services.notification_service"):
            await notification_service._paper_notify("redaction test")

        assert capsys.readouterr().out == ""
        assert leaked_token not in caplog.text
        assert leaked_url not in caplog.text
        assert "bot<redacted-telegram-token>/sendMessage" in caplog.text
    finally:
        notification_service._telegram_enabled = original_enabled
        notification_service.app = original_app
        notification_service.token = original_token


@pytest.mark.asyncio
async def test_send_message_retries_plain_text_when_markdown_parse_fails():
    original_enabled = notification_service._telegram_enabled
    original_app = notification_service.app
    original_chat_id = notification_service.chat_id

    class ParseFallbackBot:
        def __init__(self):
            self.calls = []

        async def send_message(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("parse_mode") == "Markdown":
                raise RuntimeError(
                    "Can't parse entities: can't find end of the entity "
                    "starting at byte offset 1568"
                )

    class FakeApp:
        def __init__(self):
            self.bot = ParseFallbackBot()

    fake_app = FakeApp()
    message = (
        "Order status NEEDS_MANUAL_RECONCILIATION "
        "signal_id=c8e474ce_0e32_4817 ticker=BTC-USD"
    )

    try:
        notification_service._telegram_enabled = True
        notification_service.app = fake_app
        notification_service.chat_id = "123"

        with patch(
            "src.services.dashboard_service.dashboard_state.add_message",
            new=AsyncMock(),
        ) as dashboard_add_message:
            await notification_service.send_message(message)

        assert len(fake_app.bot.calls) == 2
        assert fake_app.bot.calls[0]["parse_mode"] == "Markdown"
        assert "parse_mode" not in fake_app.bot.calls[1]
        assert fake_app.bot.calls[1]["text"] == message
        dashboard_add_message.assert_awaited_once_with("BOT", message)
    finally:
        notification_service._telegram_enabled = original_enabled
        notification_service.app = original_app
        notification_service.chat_id = original_chat_id


def test_httpx_telegram_request_logs_redact_bot_token(caplog):
    leaked_token = "123456789:SUPER_SECRET_TOKEN_VALUE_123456"
    leaked_url = f"https://api.telegram.org/bot{leaked_token}/getMe"

    caplog.set_level(logging.INFO, logger="httpx")
    logging.getLogger("httpx").info(
        'HTTP Request: POST %s "HTTP/1.1 200 OK"',
        leaked_url,
    )

    assert leaked_token not in caplog.text
    assert leaked_url not in caplog.text
    assert "api.telegram.org/bot<redacted-telegram-token>/getMe" in caplog.text


@pytest.mark.asyncio
async def test_request_approval_alpaca_paper_auto_approves_without_telegram():
    """Broker Alpaca paper: auto-approve even when Telegram is down."""
    originals = {
        "PAPER_TRADING": settings.PAPER_TRADING,
        "DEV_MODE": settings.DEV_MODE,
        "LIVE_CAPITAL_DANGER": settings.LIVE_CAPITAL_DANGER,
        "BROKERAGE_PROVIDER": settings.BROKERAGE_PROVIDER,
        "ALPACA_BASE_URL": settings.ALPACA_BASE_URL,
    }
    original_telegram_enabled = notification_service._telegram_enabled
    notification_service.pending_approvals.clear()

    try:
        settings.PAPER_TRADING = False
        settings.DEV_MODE = False
        settings.LIVE_CAPITAL_DANGER = True
        settings.BROKERAGE_PROVIDER = "ALPACA"
        settings.ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
        notification_service._telegram_enabled = False

        assert settings.is_broker_paper_trading is True
        assert settings.should_auto_approve_trades is True

        broken_send = AsyncMock(side_effect=RuntimeError("network down"))
        with patch.object(notification_service, "_paper_notify", broken_send):
            start = time.perf_counter()
            result = await notification_service.request_approval(
                "alpaca paper trade summary",
                trade_value=500.0,
                force_manual=True,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

        assert result is True
        assert elapsed_ms < 100
        assert notification_service.pending_approvals == {}
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    finally:
        for key, value in originals.items():
            setattr(settings, key, value)
        notification_service._telegram_enabled = original_telegram_enabled
        notification_service.pending_approvals.clear()


@pytest.mark.asyncio
async def test_request_approval_live_without_telegram_fails_closed():
    original_paper = settings.PAPER_TRADING
    original_dev = settings.DEV_MODE
    original_url = settings.ALPACA_BASE_URL
    original_override = settings.ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM
    original_threshold = settings.APPROVAL_THRESHOLD
    original_telegram_enabled = notification_service._telegram_enabled
    notification_service.pending_approvals.clear()

    try:
        settings.PAPER_TRADING = False
        settings.DEV_MODE = False
        # Real-money live host — must NOT hit Alpaca-paper auto-approve.
        settings.ALPACA_BASE_URL = "https://api.alpaca.markets"
        settings.ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM = False
        settings.APPROVAL_THRESHOLD = 1000.0
        notification_service._telegram_enabled = False

        assert settings.is_broker_paper_trading is False
        assert settings.should_auto_approve_trades is False

        pause_update = AsyncMock()
        set_state = AsyncMock()
        with patch.dict(
            sys.modules,
            {
                "src.services.dashboard_service": SimpleNamespace(
                    dashboard_service=SimpleNamespace(update=pause_update)
                ),
                "src.services.persistence_service": SimpleNamespace(
                    persistence_service=SimpleNamespace(set_system_state=set_state)
                ),
            },
        ):
            result = await notification_service.request_approval(
                "live trade without approval channel",
                trade_value=1.0,
            )

        assert result is False
        pause_update.assert_awaited_once_with(
            "PAUSED_REQUIRES_MANUAL_REVIEW",
            "Telegram approval channel unavailable; live execution paused.",
        )
        set_state.assert_awaited_once_with("operational_status", "PAUSED_REQUIRES_MANUAL_REVIEW")
        assert notification_service.pending_approvals == {}
    finally:
        settings.PAPER_TRADING = original_paper
        settings.DEV_MODE = original_dev
        settings.ALPACA_BASE_URL = original_url
        settings.ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM = original_override
        settings.APPROVAL_THRESHOLD = original_threshold
        notification_service._telegram_enabled = original_telegram_enabled
        notification_service.pending_approvals.clear()


@pytest.mark.asyncio
async def test_request_approval_live_without_telegram_pauses_for_manual_review_even_with_override():
    original_paper = settings.PAPER_TRADING
    original_dev = settings.DEV_MODE
    original_url = settings.ALPACA_BASE_URL
    original_override = settings.ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM
    original_threshold = settings.APPROVAL_THRESHOLD
    original_telegram_enabled = notification_service._telegram_enabled
    notification_service.pending_approvals.clear()

    try:
        settings.PAPER_TRADING = False
        settings.DEV_MODE = False
        settings.ALPACA_BASE_URL = "https://api.alpaca.markets"
        settings.ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM = True
        settings.APPROVAL_THRESHOLD = 1000.0
        notification_service._telegram_enabled = False

        assert settings.should_auto_approve_trades is False

        with patch("src.services.dashboard_service.dashboard_service.update", new=AsyncMock()) as pause_update, \
             patch("src.services.persistence_service.persistence_service.set_system_state", new=AsyncMock()) as set_state:
            result = await notification_service.request_approval(
                "live trade without approval channel",
                trade_value=1.0,
            )

        assert result is False
        pause_update.assert_awaited_once_with(
            "PAUSED_REQUIRES_MANUAL_REVIEW",
            "Telegram approval channel unavailable; live execution paused.",
        )
        set_state.assert_awaited_once_with("operational_status", "PAUSED_REQUIRES_MANUAL_REVIEW")
        assert notification_service.pending_approvals == {}
    finally:
        settings.PAPER_TRADING = original_paper
        settings.DEV_MODE = original_dev
        settings.ALPACA_BASE_URL = original_url
        settings.ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM = original_override
        settings.APPROVAL_THRESHOLD = original_threshold
        notification_service._telegram_enabled = original_telegram_enabled
        notification_service.pending_approvals.clear()
