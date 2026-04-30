import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.brokerage_service import BrokerageService


@pytest.mark.asyncio
async def test_quantity_rounding_and_limits():
    """place_value_order enforces minTradeQuantity and quantityIncrement."""
    service = BrokerageService()
    mock_metadata = {"minTradeQuantity": 0.1, "quantityIncrement": 0.05}
    mock_prices = {"AAPL": 100.0}

    with patch.object(service, "get_symbol_metadata", return_value=mock_metadata):
        with patch("src.services.data_service.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_price:
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


@pytest.mark.asyncio
async def test_missing_quantity_increment_uses_t212_safe_precision():
    service = BrokerageService()

    with patch.object(service, "get_symbol_metadata", return_value={}):
        with patch("src.services.data_service.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_price:
            mock_price.return_value = {"DUK": 127.78}
            with patch("src.services.risk_service.risk_service.calculate_friction") as mock_friction:
                mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}
                with patch.object(service.session, "post") as mock_post:
                    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"orderId": "ok"})

                    result = await service.place_value_order("DUK", 420.39, "BUY")

    assert result["orderId"] == "ok"
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["quantity"] == 3.28


@pytest.mark.asyncio
async def test_get_available_quantity_uses_positions_endpoint():
    service = BrokerageService()
    response = MagicMock(
        status_code=200,
        json=lambda: [
            {
                "instrument": {"ticker": "AAPL_US_EQ"},
                "quantity": 5.0,
                "quantityAvailableForTrading": 3.5,
                "averagePricePaid": 100.0,
            }
        ],
    )

    with patch.object(service, "_http_get", return_value=response) as mock_get:
        available = await service.get_available_quantity("AAPL")

    assert available == 3.5
    args, kwargs = mock_get.call_args
    assert args[0].endswith("/equity/positions")
    assert kwargs["params"] == {"ticker": "AAPL_US_EQ"}
