from unittest.mock import AsyncMock, patch

import pytest

from src.services.brokerage_service import BrokerageService


@pytest.mark.asyncio
async def test_live_crypto_routes_to_web3():
    service = BrokerageService()
    service.web3.place_value_order = AsyncMock(return_value={"status": "success", "order_id": "0xtx"})
    service._place_value_order_t212 = AsyncMock(return_value={"status": "success", "order_id": "t212"})

    with patch("src.services.brokerage_service.settings.PAPER_TRADING", False):
        result = await service.place_value_order("ETH-USD", 100.0, "BUY")

    assert result["order_id"] == "0xtx"
    service.web3.place_value_order.assert_awaited_once()
    service._place_value_order_t212.assert_not_awaited()


@pytest.mark.asyncio
async def test_equity_routes_to_t212():
    service = BrokerageService()
    service.web3.place_value_order = AsyncMock(return_value={"status": "success", "order_id": "0xtx"})
    service._place_value_order_t212 = AsyncMock(return_value={"status": "success", "order_id": "t212"})

    with patch("src.services.brokerage_service.settings.PAPER_TRADING", False):
        result = await service.place_value_order("AAPL", 100.0, "BUY")

    assert result["order_id"] == "t212"
    service._place_value_order_t212.assert_awaited_once()
    service.web3.place_value_order.assert_not_awaited()
