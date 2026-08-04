"""Dashboard /api surface: step-up 2FA, 2FA takeover prevention, log scrubbing."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.config import settings
from src.services.dashboard_service import (
    BotControlRequest,
    TwoFactorInitiateRequest,
    _redact_dashboard_log_line,
    app,
    dashboard_service,
    require_step_up_2fa,
    session_manager,
)


@pytest.fixture
def authed_client(monkeypatch):
    """Authenticated TestClient with a signed dashboard session (no static token)."""
    monkeypatch.setattr(
        dashboard_service.totp,
        "public_status",
        lambda: {"enabled": False, "pending_setup": False, "backup_codes_remaining": 0},
    )
    created = session_manager.create(actor="test")
    with TestClient(app) as client:
        client.headers.update({"X-Dashboard-Session": created["session_token"]})
        yield client, created["session_token"]


def test_redact_dashboard_log_line_masks_setting_secrets(monkeypatch):
    monkeypatch.setattr(settings, "ALPACA_API_SECRET", "alpaca-secret-value-xyz")
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123456:AAHsecretTelegramTokenValue")
    line = (
        "order failed alpaca-secret-value-xyz via "
        "https://api.telegram.org/bot123456:AAHsecretTelegramTokenValue/sendMessage"
    )
    scrubbed = _redact_dashboard_log_line(line)
    assert "alpaca-secret-value-xyz" not in scrubbed
    assert "AAHsecretTelegramTokenValue" not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_redact_dashboard_log_line_masks_bearer_and_api_key_assignments():
    scrubbed = _redact_dashboard_log_line(
        "Authorization: Bearer super-secret-token api_key=sk-live-abcdefg123"
    )
    assert "super-secret-token" not in scrubbed
    assert "sk-live-abcdefg123" not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_require_step_up_2fa_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(dashboard_service.totp, "public_status", lambda: {"enabled": False})
    require_step_up_2fa(None, action="bot stop")


def test_require_step_up_2fa_rejects_missing_otp_when_enabled(monkeypatch):
    monkeypatch.setattr(dashboard_service.totp, "public_status", lambda: {"enabled": True})
    monkeypatch.setattr(dashboard_service.totp, "verify_token_or_backup", lambda token: False)
    with pytest.raises(HTTPException) as exc:
        require_step_up_2fa(None, action="bot stop")
    assert exc.value.status_code == 403
    assert "2FA" in exc.value.detail


def test_require_step_up_2fa_accepts_valid_otp(monkeypatch):
    monkeypatch.setattr(dashboard_service.totp, "public_status", lambda: {"enabled": True})
    monkeypatch.setattr(dashboard_service.totp, "verify_token_or_backup", lambda token: token == "123456")
    require_step_up_2fa("123456", action="bot stop")


def test_require_step_up_2fa_skips_on_broker_paper_when_allowed(monkeypatch):
    monkeypatch.setattr(dashboard_service.totp, "public_status", lambda: {"enabled": True})
    monkeypatch.setattr(dashboard_service.totp, "verify_token_or_backup", lambda token: False)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    assert settings.should_auto_approve_trades is True
    require_step_up_2fa(None, action="wallet sync", allow_paper_skip=True)


def test_require_step_up_2fa_still_required_on_live_money(monkeypatch):
    monkeypatch.setattr(dashboard_service.totp, "public_status", lambda: {"enabled": True})
    monkeypatch.setattr(dashboard_service.totp, "verify_token_or_backup", lambda token: False)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://api.alpaca.markets")
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    assert settings.should_auto_approve_trades is False
    with pytest.raises(HTTPException) as exc:
        require_step_up_2fa(None, action="wallet sync", allow_paper_skip=True)
    assert exc.value.status_code == 403
    assert "otp_token" in exc.value.detail


def test_wallet_sync_skips_step_up_in_broker_paper(authed_client, monkeypatch):
    client, _session = authed_client
    monkeypatch.setattr(
        dashboard_service.totp,
        "public_status",
        lambda: {"enabled": True, "pending_setup": False, "backup_codes_remaining": 1},
    )
    monkeypatch.setattr(dashboard_service.totp, "verify_token_or_backup", lambda token: False)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)

    async def _fake_sync(request):
        return {"status": "ok", "mode": "ALPACA", "orders": [], "failures": 0, "skipped": []}

    monkeypatch.setattr(dashboard_service, "sync_wallet_for_coint", _fake_sync)
    resp = client.post("/api/wallet/sync", json={"budget": 25.0, "delay_seconds": 0})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_initiate_setup_allows_first_enroll_without_otp(monkeypatch):
    monkeypatch.setattr(
        dashboard_service.totp,
        "get_state",
        lambda: {
            "enabled": False,
            "pending": None,
            "secret_encrypted": None,
            "backup_code_hashes": [],
        },
    )
    saved = {}
    monkeypatch.setattr(dashboard_service.totp, "save_state", lambda state: saved.update(state))
    result = dashboard_service.totp.initiate_setup()
    assert result["secret"]
    assert result["backup_codes"]
    assert saved.get("pending")


def test_initiate_setup_blocks_rotation_without_current_otp(monkeypatch):
    monkeypatch.setattr(
        dashboard_service.totp,
        "get_state",
        lambda: {
            "enabled": True,
            "pending": None,
            "secret_encrypted": "enc",
            "backup_code_hashes": ["hash"],
        },
    )
    monkeypatch.setattr(dashboard_service.totp, "verify_token_or_backup", lambda token: False)
    with pytest.raises(HTTPException) as exc:
        dashboard_service.totp.initiate_setup()
    assert exc.value.status_code == 403
    assert "rotate" in exc.value.detail.lower()


def test_initiate_setup_rotation_requires_valid_otp(monkeypatch):
    monkeypatch.setattr(
        dashboard_service.totp,
        "get_state",
        lambda: {
            "enabled": True,
            "pending": None,
            "secret_encrypted": "enc",
            "backup_code_hashes": ["hash"],
        },
    )
    monkeypatch.setattr(dashboard_service.totp, "verify_token_or_backup", lambda token: token == "654321")
    saved = {}
    monkeypatch.setattr(dashboard_service.totp, "save_state", lambda state: saved.update(state))
    result = dashboard_service.totp.initiate_setup(otp_token="654321")
    assert result["secret"]
    assert saved.get("pending")


def test_bot_control_requires_step_up_when_2fa_enabled(authed_client, monkeypatch):
    client, _session = authed_client
    monkeypatch.setattr(
        dashboard_service.totp,
        "public_status",
        lambda: {"enabled": True, "pending_setup": False, "backup_codes_remaining": 1},
    )
    monkeypatch.setattr(dashboard_service.totp, "verify_token_or_backup", lambda token: token == "111111")

    denied = client.post("/api/bot/control", json={"action": "stop", "actor": "test"})
    assert denied.status_code == 403

    allowed = client.post(
        "/api/bot/control",
        json={"action": "stop", "actor": "test", "otp_token": "111111"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["action"] == "stop"


def test_bot_control_without_2fa_still_needs_session(monkeypatch):
    monkeypatch.setattr(
        dashboard_service.totp,
        "public_status",
        lambda: {"enabled": False, "pending_setup": False, "backup_codes_remaining": 0},
    )
    with TestClient(app) as client:
        resp = client.post("/api/bot/control", json={"action": "restart"})
    assert resp.status_code in (401, 403)


def test_wallet_buy_requires_step_up_when_2fa_enabled(authed_client, monkeypatch):
    client, _session = authed_client
    monkeypatch.setattr(
        dashboard_service.totp,
        "public_status",
        lambda: {"enabled": True, "pending_setup": False, "backup_codes_remaining": 1},
    )
    monkeypatch.setattr(dashboard_service.totp, "verify_token_or_backup", lambda token: False)
    # Live real-money: paper skip must not apply.
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://api.alpaca.markets")
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)

    resp = client.post(
        "/api/wallet/recommendations/buy",
        json={"budget": 25.0, "include_broken": False},
    )
    assert resp.status_code == 403


def test_system_logs_scrub_secrets(authed_client, monkeypatch):
    client, _session = authed_client
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-openai-should-not-leak")

    def _read_recent_logs(limit: int = 200):
        raw = ["failed with OPENAI key sk-openai-should-not-leak"]
        return {
            "file": "logs/bot.log",
            "lines": [_redact_dashboard_log_line(line) for line in raw[-limit:]],
            "events": [],
        }

    monkeypatch.setattr(dashboard_service, "read_recent_logs", _read_recent_logs)
    resp = client.get("/api/system/logs?limit=50")
    assert resp.status_code == 200
    joined = "\n".join(resp.json()["lines"])
    assert "sk-openai-should-not-leak" not in joined
    assert "[REDACTED]" in joined


def test_telegram_chat_id_is_sensitive_in_config():
    config = dashboard_service.get_dashboard_config()
    items = {item["key"]: item for item in config["items"]}
    assert items["TELEGRAM_CHAT_ID"]["sensitive"] is True
    if settings.TELEGRAM_CHAT_ID.strip():
        assert items["TELEGRAM_CHAT_ID"]["value"] == dashboard_service._mask_sensitive_value(
            settings.TELEGRAM_CHAT_ID
        )


@pytest.mark.asyncio
async def test_fail_closed_login_still_blocks_token_only():
    """Regression: login without Telegram channel and without OTP must stay 503."""
    from src.services.dashboard_service import DashboardLoginRequest, _login

    class DummyRequest:
        headers = {}
        client = None

    payload = DashboardLoginRequest(actor="dashboard", security_token="test-token")
    with patch("src.services.dashboard_service.verify_security_token", return_value=None), patch(
        "src.services.dashboard_service.login_challenge_manager.create",
        side_effect=HTTPException(status_code=503, detail="approval unavailable"),
    ), patch(
        "src.services.dashboard_service.dashboard_service.totp.public_status",
        return_value={"enabled": False},
    ):
        with pytest.raises(HTTPException) as exc:
            await _login(payload, DummyRequest())
    assert exc.value.status_code == 503


def test_request_models_accept_otp():
    assert TwoFactorInitiateRequest(otp_token="123456").otp_token == "123456"
    assert BotControlRequest(action="start", otp_token="999999").otp_token == "999999"
