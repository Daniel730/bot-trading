"""
Tests for BrokerageService dispatcher routing.

Verifies that:
  - Crypto tickers route to web3 when PAPER_TRADING=False
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
    with patch(f"src.services.brokerage_service.T212Provider"), \
         patch(f"src.services.brokerage_service.AlpacaProvider"):
        svc = BrokerageService(provider_name=provider_name)
    return svc


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_live_crypto_routes_to_web3():
    """A crypto ticker (contains -USD) must go through web3 in live mode."""
    svc = _make_service()
    svc.web3 = MagicMock()
    svc.web3.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "0xtx"}
    )
    svc.provider.place_value_order = AsyncMock(
        return_value={"status": "success", "order_id": "broker_order"}
    )

    with patch("src.services.brokerage_service.settings.PAPER_TRADING", False):
        result = await svc.place_value_order("ETH-USD", 100.0, "BUY")

    assert result["order_id"] == "0xtx"
    svc.web3.place_value_order.assert_awaited_once()
    svc.provider.place_value_order.assert_not_awaited()


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
    svc.provider.place_value_order.assert_awaited_once_with(
        "MSFT", 500.0, "BUY", None, None
    )
    svc.web3.place_value_order.assert_not_awaited()


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
