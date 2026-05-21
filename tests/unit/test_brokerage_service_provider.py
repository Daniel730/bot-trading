import importlib
from unittest.mock import patch

import pytest

from src.services.brokerage_service import BrokerageService


def test_brokerage_module_import_does_not_initialize_alpaca_provider():
    import src.services.brokerage_service as module

    with pytest.MonkeyPatch.context() as monkeypatch:
        def fail_on_init(*args, **kwargs):
            raise AssertionError("brokerage import must not initialize AlpacaProvider")

        monkeypatch.setattr("src.services.brokerage.alpaca.AlpacaProvider", fail_on_init)
        reloaded = importlib.reload(module)

    importlib.reload(reloaded)


def test_brokerage_service_always_uses_alpaca():
    with patch("src.services.brokerage_service.AlpacaProvider") as mock_alpaca:
        svc = BrokerageService(provider_name="T212")

    assert svc.provider_name == "ALPACA"
    assert svc.provider is mock_alpaca.return_value
    mock_alpaca.assert_called_once_with()


def test_get_venue_returns_alpaca_for_equity_and_crypto():
    with patch("src.services.brokerage_service.AlpacaProvider"):
        svc = BrokerageService()

    assert svc.get_venue("AAPL") == "ALPACA"
    assert svc.get_venue("BTC-USD") == "ALPACA"


def test_reconfigure_keeps_alpaca():
    with patch("src.services.brokerage_service.AlpacaProvider") as mock_alpaca:
        first_provider = object()
        second_provider = object()
        mock_alpaca.side_effect = [first_provider, second_provider]

        svc = BrokerageService()
        svc.configure_provider("WEB3")

    assert svc.provider_name == "ALPACA"
    assert svc.provider is second_provider
    assert mock_alpaca.call_count == 2
