from unittest.mock import patch

from src.services.brokerage_service import BrokerageService


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
