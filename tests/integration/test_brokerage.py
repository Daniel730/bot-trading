from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.brokerage_service import BrokerageService


@pytest.mark.asyncio
async def test_brokerage_service_places_alpaca_market_order():
    with patch("src.services.brokerage_service.AlpacaProvider"):
        service = BrokerageService("LEGACY")
    service.provider.place_market_order = AsyncMock(
        return_value={"status": "success", "order_id": "123"}
    )

    result = await service.place_market_order("KO", 1.0, "BUY")

    assert result["status"] == "success"
    assert result["venue"] == "ALPACA"
    service.provider.place_market_order.assert_awaited_once_with("KO", 1.0, "BUY", None, None)


@pytest.mark.asyncio
async def test_brokerage_service_gets_alpaca_portfolio():
    with patch("src.services.brokerage_service.AlpacaProvider"):
        service = BrokerageService()
    service.provider.get_portfolio = MagicMock(return_value=[{"ticker": "KO", "quantity": 10.0}])

    result = await service.get_portfolio()

    assert len(result) == 1
    assert result[0]["ticker"] == "KO"
