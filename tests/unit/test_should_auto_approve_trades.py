"""Unit tests for settings.should_auto_approve_trades / is_broker_paper_trading."""

from src.config import settings


def test_shadow_paper_should_auto_approve(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", True)
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    assert settings.is_broker_paper_trading is False
    assert settings.should_auto_approve_trades is True


def test_alpaca_paper_should_auto_approve(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    assert settings.is_alpaca_paper_endpoint is True
    assert settings.is_broker_paper_trading is True
    assert settings.should_auto_approve_trades is True


def test_live_real_money_should_not_auto_approve(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://api.alpaca.markets")

    assert settings.is_alpaca_paper_endpoint is False
    assert settings.is_broker_paper_trading is False
    assert settings.should_auto_approve_trades is False


def test_dev_mode_is_not_broker_paper(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "DEV_MODE", True)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    assert settings.is_broker_paper_trading is False
    assert settings.should_auto_approve_trades is False
