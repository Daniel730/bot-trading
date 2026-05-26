from unittest.mock import MagicMock

from src.config import settings
from src.services.dashboard_service import dashboard_service, dashboard_state


def test_dashboard_runtime_identifies_alpaca_paper_broker_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    runtime = dashboard_state.runtime_info()

    assert runtime["mode"] == "ALPACA_PAPER"
    assert runtime["execution_mode"] == "ALPACA_PAPER"
    assert runtime["paper_trading"] is False
    assert runtime["broker_paper_trading"] is True
    assert runtime["alpaca_endpoint_class"] == "paper"


def test_system_health_exposes_sanitized_runtime_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    health = dashboard_service.health_snapshot()
    runtime = health["runtime"]

    assert runtime["execution_mode"] == "ALPACA_PAPER"
    assert runtime["broker_paper_trading"] is True
    assert runtime["alpaca_endpoint_class"] == "paper"
    assert "paper-api.alpaca.markets" not in str(runtime)


def test_preflight_logs_sanitized_runtime_mode(monkeypatch, monitor):
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setattr("src.monitor.console.print", lambda *args, **kwargs: None)
    log_info = MagicMock()
    monkeypatch.setattr("src.monitor.logger.info", log_info)

    monitor.log_preflight()

    runtime_log = next(
        call for call in log_info.call_args_list
        if str(call.args[0]).startswith("Runtime mode resolved:")
    )
    rendered = runtime_log.args[0] % runtime_log.args[1:]

    assert "execution_mode=ALPACA_PAPER" in rendered
    assert "broker_paper_trading=True" in rendered
    assert "alpaca_endpoint_class=paper" in rendered
    assert "paper-api.alpaca.markets" not in rendered
