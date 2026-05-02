"""
Tests for BrokerageService dispatcher routing.

Verifies that:
  - Crypto tickers route to the active broker provider, not Web3
  - Equity tickers route to the active broker provider
  - The ALPACA provider path is exercised correctly
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.brokerage_service import BrokerageService


# ---------------------------------------------------------------------------
# Helper: build a service with a fully-mocked provider so no real API calls
# are made during unit tests.
# ---------------------------------------------------------------------------

def _make_service(provider_name: str = "T212") -> BrokerageService:
    """
    Create a BrokerageService instance with external provider constructors patched for testing.
    
    Parameters:
        provider_name (str): The provider name to pass to BrokerageService (e.g., "T212" or "ALPACA").
    
    Returns:
        BrokerageService: An instance of BrokerageService where T212Provider and AlpacaProvider are patched to prevent real provider construction or network calls.
    """
    with patch(f"src.services.brokerage_service.T212Provider"), \
         patch(f"src.services.brokerage_service.AlpacaProvider"):
        svc = BrokerageService(provider_name=provider_name)
    return svc


def test_default_provider_uses_settings_brokerage_provider():
    """The default BrokerageService constructor should honor BROKERAGE_PROVIDER."""
    with patch("src.services.brokerage_service.settings.BROKERAGE_PROVIDER", "ALPACA"), \
         patch("src.services.brokerage_service.T212Provider") as mock_t212, \
         patch("src.services.brokerage_service.AlpacaProvider") as mock_alpaca:
        svc = BrokerageService()

    assert svc.provider_name == "ALPACA"
    assert svc.provider is mock_alpaca.return_value
    mock_alpaca.assert_called_once_with()
    mock_t212.assert_not_called()


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_live_crypto_routes_to_active_alpaca_provider():
    """A crypto ticker (contains -USD) must go through Alpaca in live mode."""
    svc = _make_service(provider_name="ALPACA")
    svc.web3 = MagicMock()
    svc.web3.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "0xtx"}
    )
    svc.provider.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "alpaca_crypto_order"}
    )

    with patch("src.services.brokerage_service.settings.PAPER_TRADING", False):
        result = await svc.place_value_order("ETH-USD", 100.0, "BUY")

    assert result["order_id"] == "alpaca_crypto_order"
    assert result["venue"] == "ALPACA"
    svc.provider.place_value_order.assert_awaited_once_with(
        "ETH-USD", 100.0, "BUY", None, None
    )
    svc.web3.place_value_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_equity_routes_to_t212_provider():
    """An equity ticker must be dispatched to the active broker provider (T212)."""
    svc = _make_service(provider_name="T212")
    svc.web3 = MagicMock()
    svc.web3.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "0xtx"}
    )
    svc.provider.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "t212_order"}
    )

    with patch("src.services.brokerage_service.settings.PAPER_TRADING", False):
        result = await svc.place_value_order("AAPL", 100.0, "BUY")

    assert result["order_id"] == "t212_order"
    svc.provider.place_value_order.assert_awaited_once()
    svc.web3.place_value_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_equity_routes_to_alpaca_provider():
    """When BROKERAGE_PROVIDER=ALPACA, equity orders go to the Alpaca provider."""
    svc = _make_service(provider_name="ALPACA")
    svc.web3 = MagicMock()
    svc.web3.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "0xtx"}
    )
    svc.provider.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "alpaca_order"}
    )

    with patch("src.services.brokerage_service.settings.PAPER_TRADING", False):
        result = await svc.place_value_order("MSFT", 500.0, "BUY")

    assert result["order_id"] == "alpaca_order"
    assert result["venue"] == "ALPACA"
    svc.provider.place_value_order.assert_awaited_once_with(
        "MSFT", 500.0, "BUY", None, None
    )
    svc.web3.place_value_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_alpaca_live_success_updates_alpaca_budget():
    """Successful live Alpaca value orders update the ALPACA venue budget key."""
    svc = _make_service(provider_name="ALPACA")
    svc.provider.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "alpaca_order"}
    )

    with patch("src.services.brokerage_service.settings.PAPER_TRADING", False), \
         patch("src.services.brokerage_service.budget_service.update_used_budget") as mock_budget:
        result = await svc.place_value_order("MSFT", 500.0, "BUY")

    assert result["venue"] == "ALPACA"
    mock_budget.assert_called_once_with("ALPACA", 500.0)


@pytest.mark.asyncio
async def test_alpaca_live_error_does_not_update_budget():
    """Failed Alpaca orders must not consume venue budget."""
    svc = _make_service(provider_name="ALPACA")
    svc.provider.place_value_order = AsyncMock(
        return_value={"status": "error", "message": "broker rejected"}
    )

    with patch("src.services.brokerage_service.settings.PAPER_TRADING", False), \
         patch("src.services.brokerage_service.budget_service.update_used_budget") as mock_budget:
        result = await svc.place_value_order("MSFT", 500.0, "BUY")

    assert result["venue"] == "ALPACA"
    mock_budget.assert_not_called()


@pytest.mark.asyncio
async def test_paper_trading_crypto_does_not_route_to_web3():
    """In paper-trading mode, even a crypto ticker must use the broker provider."""
    svc = _make_service()
    svc.web3 = MagicMock()
    svc.web3.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "0xtx"}
    )
    svc.provider.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "paper_order"}
    )

    with patch("src.services.brokerage_service.settings.PAPER_TRADING", True):
        result = await svc.place_value_order("BTC-USD", 100.0, "BUY")

    # web3 path is guarded by `not settings.PAPER_TRADING`, so provider wins
    svc.web3.place_value_order.assert_not_awaited()
    svc.provider.place_value_order.assert_awaited_once()
