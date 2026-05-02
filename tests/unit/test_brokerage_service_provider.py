"""
Unit tests for BrokerageService.configure_provider() introduced in this PR.

The new method extracts provider selection logic from __init__ and allows
the active equity brokerage to be swapped at runtime without restarting
the process.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.services.brokerage_service import BrokerageService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(provider_name: str = None, setting_value: str = "T212") -> BrokerageService:
    """
    Create a BrokerageService instance with T212 and Alpaca providers and the settings.BROKERAGE_PROVIDER value patched for tests.
    
    Parameters:
        provider_name (str | None): Optional explicit provider name passed to BrokerageService; if None, the patched setting_value is used.
        setting_value (str): Value to assign to the patched settings.BROKERAGE_PROVIDER.
    
    Returns:
        tuple: (svc, mock_t212, mock_alpaca) where `svc` is the created BrokerageService, and `mock_t212` and `mock_alpaca` are the patched provider classes (mocks).
    """
    with (
        patch("src.services.brokerage_service.T212Provider") as mock_t212,
        patch("src.services.brokerage_service.AlpacaProvider") as mock_alpaca,
        patch("src.services.brokerage_service.settings") as mock_settings,
    ):
        mock_settings.BROKERAGE_PROVIDER = setting_value
        svc = BrokerageService(provider_name=provider_name)
        return svc, mock_t212, mock_alpaca


# ---------------------------------------------------------------------------
# configure_provider – provider selection
# ---------------------------------------------------------------------------

class TestConfigureProviderSelection:
    def test_defaults_to_t212_when_setting_is_t212(self):
        with (
            patch("src.services.brokerage_service.T212Provider") as mock_t212,
            patch("src.services.brokerage_service.AlpacaProvider"),
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = "T212"
            svc = BrokerageService()

        assert svc.provider_name == "T212"
        mock_t212.assert_called_once()

    def test_selects_alpaca_when_setting_is_alpaca(self):
        with (
            patch("src.services.brokerage_service.T212Provider"),
            patch("src.services.brokerage_service.AlpacaProvider") as mock_alpaca,
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = "ALPACA"
            svc = BrokerageService()

        assert svc.provider_name == "ALPACA"
        mock_alpaca.assert_called_once()

    def test_explicit_provider_name_overrides_setting(self):
        with (
            patch("src.services.brokerage_service.T212Provider"),
            patch("src.services.brokerage_service.AlpacaProvider") as mock_alpaca,
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = "T212"
            svc = BrokerageService(provider_name="ALPACA")

        assert svc.provider_name == "ALPACA"
        mock_alpaca.assert_called_once()

    def test_unknown_provider_falls_back_to_t212(self):
        with (
            patch("src.services.brokerage_service.T212Provider") as mock_t212,
            patch("src.services.brokerage_service.AlpacaProvider"),
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = "SOME_OTHER_BROKER"
            svc = BrokerageService()

        # Anything that is not ALPACA gets normalised to T212
        assert svc.provider_name == "T212"
        mock_t212.assert_called_once()

    def test_none_setting_falls_back_to_t212(self):
        with (
            patch("src.services.brokerage_service.T212Provider") as mock_t212,
            patch("src.services.brokerage_service.AlpacaProvider"),
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = None
            svc = BrokerageService()

        assert svc.provider_name == "T212"
        mock_t212.assert_called_once()

    def test_empty_string_setting_falls_back_to_t212(self):
        with (
            patch("src.services.brokerage_service.T212Provider") as mock_t212,
            patch("src.services.brokerage_service.AlpacaProvider"),
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = ""
            svc = BrokerageService()

        assert svc.provider_name == "T212"
        mock_t212.assert_called_once()

    def test_provider_name_is_normalised_to_uppercase(self):
        """Provider strings like 'alpaca' should be uppercased before comparison."""
        with (
            patch("src.services.brokerage_service.T212Provider"),
            patch("src.services.brokerage_service.AlpacaProvider") as mock_alpaca,
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = "alpaca"
            svc = BrokerageService()

        assert svc.provider_name == "ALPACA"
        mock_alpaca.assert_called_once()

    def test_provider_name_strips_whitespace(self):
        """Provider strings with surrounding spaces should be trimmed."""
        with (
            patch("src.services.brokerage_service.T212Provider"),
            patch("src.services.brokerage_service.AlpacaProvider") as mock_alpaca,
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = "  ALPACA  "
            svc = BrokerageService()

        assert svc.provider_name == "ALPACA"
        mock_alpaca.assert_called_once()


# ---------------------------------------------------------------------------
# configure_provider – runtime reconfiguration
# ---------------------------------------------------------------------------

class TestConfigureProviderRuntimeSwap:
    def test_reconfigure_from_t212_to_alpaca(self):
        with (
            patch("src.services.brokerage_service.T212Provider"),
            patch("src.services.brokerage_service.AlpacaProvider") as mock_alpaca,
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = "T212"
            svc = BrokerageService()

            # Simulate a runtime config change
            mock_settings.BROKERAGE_PROVIDER = "ALPACA"
            svc.configure_provider()

        assert svc.provider_name == "ALPACA"
        mock_alpaca.assert_called_once()

    def test_reconfigure_from_alpaca_to_t212(self):
        with (
            patch("src.services.brokerage_service.T212Provider") as mock_t212,
            patch("src.services.brokerage_service.AlpacaProvider"),
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = "ALPACA"
            svc = BrokerageService()

            mock_settings.BROKERAGE_PROVIDER = "T212"
            svc.configure_provider()

        assert svc.provider_name == "T212"
        # Called once during __init__ (ALPACA path) and once for configure (T212 path)
        mock_t212.assert_called_once()

    def test_explicit_override_in_configure_provider(self):
        with (
            patch("src.services.brokerage_service.T212Provider"),
            patch("src.services.brokerage_service.AlpacaProvider") as mock_alpaca,
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = "T212"
            svc = BrokerageService()
            svc.configure_provider("ALPACA")

        assert svc.provider_name == "ALPACA"
        mock_alpaca.assert_called_once()

    def test_provider_object_is_replaced_on_reconfigure(self):
        """
        Verifies that reconfiguring the brokerage provider replaces the service's provider instance.
        
        After switching the configured provider and calling configure_provider(), the service's `provider`
        attribute refers to a different object than it did before reconfiguration.
        """
        with (
            patch("src.services.brokerage_service.T212Provider") as mock_t212,
            patch("src.services.brokerage_service.AlpacaProvider") as mock_alpaca,
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = "T212"
            mock_t212.return_value = MagicMock(name="t212_provider_instance")
            mock_alpaca.return_value = MagicMock(name="alpaca_provider_instance")

            svc = BrokerageService()
            old_provider = svc.provider

            mock_settings.BROKERAGE_PROVIDER = "ALPACA"
            svc.configure_provider()
            new_provider = svc.provider

        assert old_provider is not new_provider


# ---------------------------------------------------------------------------
# get_venue – routes all bot trades through the configured broker
# ---------------------------------------------------------------------------

class TestGetVenueWithActiveProvider:
    def _service_with_provider(self, provider_name: str) -> BrokerageService:
        with (
            patch("src.services.brokerage_service.T212Provider"),
            patch("src.services.brokerage_service.AlpacaProvider"),
            patch("src.services.brokerage_service.settings") as mock_settings,
        ):
            mock_settings.BROKERAGE_PROVIDER = provider_name
            return BrokerageService()

    def test_crypto_ticker_routes_to_active_t212_provider(self):
        svc = self._service_with_provider("T212")
        assert svc.get_venue("BTC-USD") == "T212"

    def test_crypto_ticker_routes_to_active_alpaca_provider(self):
        svc = self._service_with_provider("ALPACA")
        assert svc.get_venue("ETH-USD") == "ALPACA"

    def test_equity_ticker_routes_to_active_t212_provider(self):
        svc = self._service_with_provider("T212")
        assert svc.get_venue("AAPL") == "T212"

    def test_equity_ticker_routes_to_active_alpaca_provider(self):
        svc = self._service_with_provider("ALPACA")
        assert svc.get_venue("MSFT") == "ALPACA"

    def test_case_insensitive_crypto_detection(self):
        svc = self._service_with_provider("T212")
        assert svc.get_venue("btc-usd") == "T212"
