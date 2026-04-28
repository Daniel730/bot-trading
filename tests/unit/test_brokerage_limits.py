import pytest
from unittest.mock import AsyncMock, patch

from src.services.brokerage_service import BrokerageService


@pytest.mark.asyncio
async def test_quantity_rounding_and_limits():
    """place_value_order enforces minTradeQuantity and quantityIncrement."""
    service = BrokerageService()
    mock_metadata = {"minTradeQuantity": 0.1, "quantityIncrement": 0.05}
    mock_prices = {"AAPL": 100.0}

    with patch.object(service, "get_symbol_metadata", return_value=mock_metadata):
        with patch("src.services.data_service.data_service.get_latest_price", new_callable=AsyncMock) as mock_price:
            mock_price.return_value = mock_prices
            with patch("src.services.risk_service.risk_service.calculate_friction") as mock_friction:
                mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}

                with patch.object(service, "place_market_order", new_callable=AsyncMock) as mock_place:
                    mock_place.return_value = {"status": "filled"}
                    result = await service.place_value_order("AAPL", 172.0, "BUY")

                    assert result["status"] == "filled"
                    mock_place.assert_called_once()
                    args, _ = mock_place.call_args
                    assert args[1] == 1.70

                mock_metadata["minTradeQuantity"] = 0.2
                mock_prices["AAPL"] = 1000.0
                with patch.object(service, "place_market_order", new_callable=AsyncMock) as mock_place:
                    result = await service.place_value_order("AAPL", 100.0, "BUY")

                    assert result["status"] == "error"
                    assert "minTradeQuantity" in result["message"]
                    mock_place.assert_not_called()
