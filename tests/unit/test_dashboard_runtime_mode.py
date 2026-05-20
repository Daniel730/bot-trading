from src.config import settings
from src.services.dashboard_service import dashboard_state


def test_dashboard_runtime_identifies_alpaca_paper_broker_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    runtime = dashboard_state.runtime_info()

    assert runtime["mode"] == "ALPACA_PAPER"
    assert runtime["paper_trading"] is False
    assert runtime["broker_paper_trading"] is True

