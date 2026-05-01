import pytest
from fastapi import HTTPException

from src.services.dashboard_service import dashboard_service


def test_dashboard_config_exposes_alpaca_broker_settings():
    config = dashboard_service.get_dashboard_config()
    items = {item["key"]: item for item in config["items"]}

    assert items["BROKERAGE_PROVIDER"]["options"] == ["T212", "ALPACA"]
    assert items["BROKERAGE_PROVIDER"]["sensitive"] is True
    assert items["BROKERAGE_PROVIDER"]["value"] in {"T212", "ALPACA"}
    assert items["TRADING_212_MODE"]["options"] == ["demo", "live"]
    assert isinstance(items["ALPACA_BASE_URL"]["value"], str)
    assert items["ALPACA_BASE_URL"]["value"] != "********"
    assert items["ALPACA_API_KEY"]["sensitive"] is True
    assert items["ALPACA_API_SECRET"]["sensitive"] is True
    assert items["ALPACA_BASE_URL"]["sensitive"] is True


def test_dashboard_config_validates_brokerage_provider_options():
    assert dashboard_service._coerce_config_value("BROKERAGE_PROVIDER", "alpaca") == "ALPACA"
    assert dashboard_service._coerce_config_value("TRADING_212_MODE", "LIVE") == "live"

    with pytest.raises(HTTPException):
        dashboard_service._coerce_config_value("BROKERAGE_PROVIDER", "IBKR")
