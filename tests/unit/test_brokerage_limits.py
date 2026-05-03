from unittest.mock import patch

import pytest

from src.services.brokerage_service import BrokerageService


@pytest.mark.asyncio
async def test_get_available_quantity_uses_alpaca_positions_endpoint():
    with patch("src.services.brokerage_service.AlpacaProvider"):
        service = BrokerageService()

    service.provider.get_positions.return_value = [
        {
            "ticker": "AAPL",
            "quantity": 5.0,
            "quantityAvailableForTrading": 3.5,
            "averagePrice": 100.0,
        }
    ]

    available = await service.get_available_quantity("AAPL")

    assert available == 3.5


def test_symbol_metadata_is_delegated_to_alpaca_provider():
    with patch("src.services.brokerage_service.AlpacaProvider"):
        service = BrokerageService()

    service.provider.get_symbol_metadata.return_value = {
        "ticker": "MSFT",
        "minTradeQuantity": 0.0001,
        "quantityIncrement": 0.0001,
        "tickSize": 0.01,
        "status": "active",
    }

    assert service.get_symbol_metadata("MSFT")["quantityIncrement"] == 0.0001
