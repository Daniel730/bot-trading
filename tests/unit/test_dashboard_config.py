import pytest
from fastapi import HTTPException

from src.config import settings
from src.services.dashboard_service import dashboard_service


def test_dashboard_config_exposes_alpaca_broker_settings():
    config = dashboard_service.get_dashboard_config()
    items = {item["key"]: item for item in config["items"]}

    assert items["BROKERAGE_PROVIDER"]["options"] == ["ALPACA"]
    assert items["BROKERAGE_PROVIDER"]["sensitive"] is True
    assert items["BROKERAGE_PROVIDER"]["value"] == "ALPACA"
    assert "TRADING_212_MODE" not in items
    assert "ALPACA_BUDGET_USD" in items
    assert isinstance(items["ALPACA_BASE_URL"]["value"], str)
    assert items["ALPACA_BASE_URL"]["value"] != "********"
    assert items["ALPACA_API_KEY"]["sensitive"] is True
    assert items["ALPACA_API_SECRET"]["sensitive"] is True
    assert items["ALPACA_BASE_URL"]["sensitive"] is True


def test_dashboard_config_validates_brokerage_provider_options():
    assert dashboard_service._coerce_config_value("BROKERAGE_PROVIDER", "alpaca") == "ALPACA"

    with pytest.raises(HTTPException):
        dashboard_service._coerce_config_value("BROKERAGE_PROVIDER", "IBKR")



def test_dashboard_config_disallows_live_approval_override_runtime_edits():
    config = dashboard_service.get_dashboard_config()
    items = {item["key"]: item for item in config["items"]}
    assert "ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM" not in items

    with pytest.raises(HTTPException):
        dashboard_service._coerce_config_value("ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM", True)


def test_dashboard_config_exposes_take_profit_force_exit():
    config = dashboard_service.get_dashboard_config()
    items = {item["key"]: item for item in config["items"]}

    assert "TAKE_PROFIT_FORCE_EXIT_ZSCORE" in items
    assert items["TAKE_PROFIT_FORCE_EXIT_ZSCORE"]["sensitive"] is False
    assert items["TAKE_PROFIT_FORCE_EXIT_ZSCORE"]["value"] == settings.TAKE_PROFIT_FORCE_EXIT_ZSCORE


@pytest.mark.asyncio
async def test_dashboard_config_clamps_dangerous_entry_zscore(monkeypatch):
    """bot_settings / dashboard must not leave MONITOR_ENTRY_ZSCORE < 1.0 on settings."""
    monkeypatch.setattr(settings, "MONITOR_ENTRY_ZSCORE", 2.0)
    monkeypatch.setattr(dashboard_service, "get_dashboard_config", lambda: {"ok": True})

    saved_overrides = []
    monkeypatch.setattr(
        "src.services.dashboard_service.save_settings_override",
        lambda update: saved_overrides.append(dict(update)),
    )
    monkeypatch.setattr(
        dashboard_service.persistence,
        "log_config_change",
        lambda **entry: None,
    )

    async def add_message(*args, **kwargs):
        return None

    monkeypatch.setattr(dashboard_service.dashboard_state, "add_message", add_message)

    await dashboard_service.update_dashboard_config(
        actor="test",
        updates={"MONITOR_ENTRY_ZSCORE": 0.5},
        otp_token=None,
    )

    assert settings.MONITOR_ENTRY_ZSCORE == 1.0
    assert saved_overrides == [{"MONITOR_ENTRY_ZSCORE": 1.0}]


@pytest.mark.asyncio
async def test_dashboard_config_rejects_live_mode_without_live_capital_danger(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", True)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", False)
    monkeypatch.setattr(dashboard_service.totp, "public_status", lambda: {"enabled": True})
    monkeypatch.setattr(dashboard_service.totp, "verify_token_or_backup", lambda token: True)
    monkeypatch.setattr(dashboard_service, "get_dashboard_config", lambda: {})

    saved_overrides = []
    audit_entries = []
    monkeypatch.setattr(
        "src.services.dashboard_service.save_settings_override",
        lambda update: saved_overrides.append(update),
    )
    monkeypatch.setattr(
        dashboard_service.persistence,
        "log_config_change",
        lambda **entry: audit_entries.append(entry),
    )

    async def add_message(*args, **kwargs):
        raise AssertionError("invalid live-mode updates must fail before dashboard broadcast")

    monkeypatch.setattr(dashboard_service.dashboard_state, "add_message", add_message)

    with pytest.raises(HTTPException) as exc:
        await dashboard_service.update_dashboard_config(
            actor="test",
            updates={"PAPER_TRADING": False},
            otp_token="123456",
        )

    assert exc.value.status_code == 400
    assert "PAPER_TRADING=false requires LIVE_CAPITAL_DANGER=true" in exc.value.detail
    assert settings.PAPER_TRADING is True
    assert settings.LIVE_CAPITAL_DANGER is False
    assert saved_overrides == []
    assert audit_entries == []
