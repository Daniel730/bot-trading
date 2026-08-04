"""Telegram empty-token / placeholder / InvalidToken safety + alert dedupe."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import notification_service as ns_mod
from src.services.notification_service import (
    NotificationService,
    _is_fatal_telegram_auth_error,
    _is_usable_telegram_token,
)


@pytest.mark.parametrize(
    "token,usable",
    [
        ("", False),
        ("   ", False),
        ("None", False),
        ("none", False),
        ("your_bot_token", False),
        ("YOUR_BOT_TOKEN", False),
        ("your_token_here", False),
        ("YOUR_TELEGRAM_BOT_TOKEN", False),
        ("changeme", False),
        ("123:abc", False),  # wrong shape
        ("123456:ABCDEFGHIJKLMNOPQRSTUV", True),
        ("7123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw", True),
    ],
)
def test_is_usable_telegram_token(token, usable):
    assert _is_usable_telegram_token(token) is usable


def test_fatal_auth_error_detection():
    from telegram.error import InvalidToken, Forbidden

    assert _is_fatal_telegram_auth_error(InvalidToken("bad")) is True
    assert _is_fatal_telegram_auth_error(Forbidden("blocked")) is True
    assert _is_fatal_telegram_auth_error(RuntimeError("network down")) is False
    assert _is_fatal_telegram_auth_error(RuntimeError("token was rejected by the server")) is True


def _service_with_token(token: str) -> NotificationService:
    with patch.object(ns_mod.settings, "TELEGRAM_BOT_TOKEN", token), patch.object(
        ns_mod.settings, "TELEGRAM_CHAT_ID", "12345"
    ):
        return NotificationService()


def test_empty_token_stays_console_only(capsys):
    service = _service_with_token("")
    assert service._telegram_enabled is False
    assert service.app is None
    out = capsys.readouterr().out
    assert "Telegram notifications disabled" in out


def test_template_your_bot_token_stays_console_only(capsys):
    """Regression: .env.template uses your_bot_token — must not enable Telegram."""
    service = _service_with_token("your_bot_token")
    assert service._telegram_enabled is False
    assert service.app is None
    out = capsys.readouterr().out
    assert "Telegram notifications disabled" in out


def test_malformed_token_never_builds_application():
    with patch.object(ns_mod, "ApplicationBuilder") as builder:
        service = _service_with_token("not-a-real-token")
        assert service._telegram_enabled is False
        builder.assert_not_called()


@pytest.mark.asyncio
async def test_start_listening_empty_token_is_noop(capsys):
    service = _service_with_token("")
    await service.start_listening()
    out = capsys.readouterr().out
    assert "console-only" in out


@pytest.mark.asyncio
async def test_start_listening_invalid_token_disables_without_raising():
    service = _service_with_token("7123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")
    # Force a shape-valid token path with a fake app that fails like InvalidToken.
    from telegram.error import InvalidToken

    fake_app = MagicMock()
    fake_app.initialize = AsyncMock(side_effect=InvalidToken("rejected"))
    fake_app.shutdown = AsyncMock()
    fake_app.running = False
    fake_app.updater = SimpleNamespace(running=False, stop=AsyncMock())
    service.app = fake_app
    service._telegram_enabled = True

    await service.start_listening()

    assert service._telegram_enabled is False
    fake_app.initialize.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_message_console_fallback_when_disabled(capsys):
    service = _service_with_token("")
    with patch(
        "src.services.dashboard_service.dashboard_state.add_message",
        new=AsyncMock(),
    ) as dash:
        await service.send_message("hello console", force=True)

    assert "[BOT MSG] hello console" in capsys.readouterr().out
    dash.assert_awaited_once_with("BOT", "hello console")


@pytest.mark.asyncio
async def test_send_message_dedupes_identical_alerts():
    service = _service_with_token("")
    service._alert_dedupe_seconds = 60.0
    with patch(
        "src.services.dashboard_service.dashboard_state.add_message",
        new=AsyncMock(),
    ) as dash:
        await service.send_message("COINTEGRATION BREAK: A/B", force=False)
        await service.send_message("COINTEGRATION BREAK: A/B", force=False)
        await service.send_message("COINTEGRATION BREAK: A/B", force=True)

    # First + forced third; middle duplicate suppressed.
    assert dash.await_count == 2


@pytest.mark.asyncio
async def test_send_message_invalid_token_disables_telegram(capsys):
    from telegram.error import InvalidToken

    service = _service_with_token("7123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")
    service._telegram_enabled = True

    class FailingBot:
        async def send_message(self, **_kwargs):
            raise InvalidToken("rejected")

    service.app = SimpleNamespace(bot=FailingBot())

    with patch(
        "src.services.dashboard_service.dashboard_state.add_message",
        new=AsyncMock(),
    ) as dash:
        await service.send_message("alert after bad token", force=True)

    assert service._telegram_enabled is False
    assert "[BOT MSG] alert after bad token" in capsys.readouterr().out
    dash.assert_awaited()


@pytest.mark.asyncio
async def test_callback_resolves_pending_approval():
    service = _service_with_token("")
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    service.pending_approvals["abc12345"] = future
    service.pending_approval_summaries["abc12345"] = "trade"
    service.chat_id = "99"

    query = MagicMock()
    query.from_user.id = 99
    query.from_user.username = "op"
    query.data = "approve:abc12345"
    query.message.text = "APPROVAL REQUIRED"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update = SimpleNamespace(callback_query=query)

    await service._handle_callback(update, MagicMock())

    assert future.done() and future.result() is True
    assert "abc12345" not in service.pending_approvals
    query.edit_message_text.assert_awaited()
    assert "APROVADO" in query.edit_message_text.await_args.kwargs.get("text", "") or (
        "APROVADO" in query.edit_message_text.await_args.args[0]
        if query.edit_message_text.await_args.args
        else "APROVADO" in query.edit_message_text.await_args.kwargs["text"]
    )


@pytest.mark.asyncio
async def test_callback_expired_correlation_acknowledged():
    service = _service_with_token("")
    service.chat_id = "99"

    query = MagicMock()
    query.from_user.id = 99
    query.from_user.username = "op"
    query.data = "approve:deadbeef"
    query.message.text = "old approval"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update = SimpleNamespace(callback_query=query)

    await service._handle_callback(update, MagicMock())

    query.edit_message_text.assert_awaited()
    edited = query.edit_message_text.await_args.kwargs.get("text") or (
        query.edit_message_text.await_args.args[0]
        if query.edit_message_text.await_args.args
        else ""
    )
    assert "expired or already resolved" in edited


@pytest.mark.asyncio
async def test_callback_unauthorized_rejected():
    service = _service_with_token("")
    service.chat_id = "99"

    query = MagicMock()
    query.from_user.id = 1
    query.from_user.username = "intruder"
    query.data = "approve:abc"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update = SimpleNamespace(callback_query=query)

    await service._handle_callback(update, MagicMock())

    query.answer.assert_awaited_once_with("⛔ Unauthorized.", show_alert=True)
    query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_paper_notify_dedupes_external_spam(capsys):
    service = _service_with_token("")
    service._telegram_enabled = False
    service._alert_dedupe_seconds = 60.0

    with patch(
        "src.services.dashboard_service.dashboard_state.add_message",
        new=AsyncMock(),
    ) as dash:
        await service._paper_notify("same summary")
        await service._paper_notify("same summary")

    out = capsys.readouterr().out
    assert out.count("[PAPER TRADE]") == 1
    assert dash.await_count == 2
