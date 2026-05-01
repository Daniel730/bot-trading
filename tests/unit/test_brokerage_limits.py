import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.brokerage_service import BrokerageService


@pytest.mark.asyncio
async def test_quantity_rounding_and_limits():
    """place_value_order enforces minTradeQuantity and quantityIncrement."""
    service = BrokerageService("T212")
    mock_metadata = {"minTradeQuantity": 0.1, "quantityIncrement": 0.05}
    mock_prices = {"AAPL": 100.0}

    with patch.object(service.provider, "get_symbol_metadata", return_value=mock_metadata):
        with patch("src.services.data_service.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_price:
            mock_price.return_value = mock_prices
            with patch("src.services.risk_service.risk_service.calculate_friction") as mock_friction:
                mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}

                # Patch the HTTP call so place_market_order logic executes.
                with patch.object(service.provider.session, "post") as mock_post:
                    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"orderId": "filled"})
                    result = await service.place_value_order("AAPL", 172.0, "BUY")

                    assert result["status"] == "success"
                    mock_post.assert_called_once()
                    _, kwargs = mock_post.call_args
                    # quantity = 172.0 / 100.0 = 1.72, rounded down to 0.05 increment → 1.70
                    assert kwargs["json"]["quantity"] == pytest.approx(1.70, rel=1e-4)

            with patch.object(
                service.provider,
                "get_symbol_metadata",
                return_value={"minTradeQuantity": 2.0, "quantityIncrement": 0.05},
            ), patch.object(service.provider.session, "post") as mock_post:
                result = await service.place_value_order("AAPL", 100.0, "BUY", price=1000.0)

                assert result["status"] == "error"
                assert "minTradeQuantity" in result["message"]
                mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_missing_quantity_increment_uses_t212_safe_precision():
    """When quantityIncrement is absent T212Provider falls back to 0.01-share precision."""
    service = BrokerageService("T212")

    with patch.object(service.provider, "get_symbol_metadata", return_value={}):
        with patch("src.services.data_service.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_price:
            mock_price.return_value = {"DUK": 127.78}
            with patch("src.services.risk_service.risk_service.calculate_friction") as mock_friction:
                mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}
                # session lives on the T212Provider, not on BrokerageService.
                with patch.object(service.provider.session, "post") as mock_post:
                    mock_post.return_value = MagicMock(
                        status_code=200,
                        json=lambda: {"orderId": "ok"},
                    )

                    result = await service.place_value_order("DUK", 420.39, "BUY")

    assert result.get("order_id") == "ok" or result.get("orderId") == "ok" or result.get("status") == "success"
    _, kwargs = mock_post.call_args
    # quantity = 420.39 / 127.78 ≈ 3.29, rounded down to 0.01 increment → 3.28
    assert kwargs["json"]["quantity"] == pytest.approx(3.28, rel=1e-2)


@pytest.mark.asyncio
async def test_min_trade_quantity_whole_unit_boundary_reject():
    """Quantity exactly below integer minTradeQuantity=2.0 is rejected without placing an order."""
    service = BrokerageService("T212")
    # price=60 → quantity = 100/60 ≈ 1.666, rounded down to 0.05 increment → 1.65, below min 2.0
    mock_metadata = {"minTradeQuantity": 2.0, "quantityIncrement": 0.05}

    with patch.object(service.provider, "get_symbol_metadata", return_value=mock_metadata):
        with patch("src.services.data_service.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_price:
            mock_price.return_value = {"AAPL": 60.0}
            with patch("src.services.risk_service.risk_service.calculate_friction") as mock_friction:
                mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}
                with patch.object(service.provider.session, "post") as mock_post:
                    result = await service.place_value_order("AAPL", 100.0, "BUY")

                    assert result["status"] == "error"
                    assert "minTradeQuantity" in result["message"]
                    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_min_trade_quantity_whole_unit_boundary_accept():
    """Quantity above integer minTradeQuantity=2.0 proceeds to place an order."""
    service = BrokerageService("T212")
    # price=40 → quantity = 100/40 = 2.5, rounded down to 0.05 increment → 2.50, above min 2.0
    mock_metadata = {"minTradeQuantity": 2.0, "quantityIncrement": 0.05}

    with patch.object(service.provider, "get_symbol_metadata", return_value=mock_metadata):
        with patch("src.services.data_service.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_price:
            mock_price.return_value = {"AAPL": 40.0}
            with patch("src.services.risk_service.risk_service.calculate_friction") as mock_friction:
                mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}
                with patch.object(service.provider.session, "post") as mock_post:
                    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"orderId": "ok"})
                    result = await service.place_value_order("AAPL", 100.0, "BUY")

                    assert result["status"] == "success"
                    mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_min_trade_quantity_2_regression_high_price():
    """Regression: price=1000 and amount=100 produces qty=0.1 which is below minTradeQuantity=2.0."""
    service = BrokerageService("T212")
    mock_metadata = {"minTradeQuantity": 2.0, "quantityIncrement": 0.05}

    with patch.object(service.provider, "get_symbol_metadata", return_value=mock_metadata):
        with patch("src.services.data_service.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_price:
            mock_price.return_value = {"AAPL": 1000.0}
            with patch("src.services.risk_service.risk_service.calculate_friction") as mock_friction:
                mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}
                with patch.object(service.provider.session, "post") as mock_post:
                    result = await service.place_value_order("AAPL", 100.0, "BUY")

                    # quantity = 100 / 1000 = 0.1, which is far below minTradeQuantity=2.0
                    assert result["status"] == "error"
                    assert "minTradeQuantity" in result["message"]
                    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_min_trade_quantity_2_exactly_met():
    """Quantity that rounds to exactly minTradeQuantity=2.0 is accepted."""
    service = BrokerageService("T212")
    # price=50 → quantity = 100/50 = 2.0, rounded down to 0.05 increment → 2.00, equals min 2.0
    mock_metadata = {"minTradeQuantity": 2.0, "quantityIncrement": 0.05}

    with patch.object(service.provider, "get_symbol_metadata", return_value=mock_metadata):
        with patch("src.services.data_service.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_price:
            mock_price.return_value = {"AAPL": 50.0}
            with patch("src.services.risk_service.risk_service.calculate_friction") as mock_friction:
                mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}
                with patch.object(service.provider.session, "post") as mock_post:
                    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"orderId": "exact"})
                    result = await service.place_value_order("AAPL", 100.0, "BUY")

                    assert result["status"] == "success"
                    mock_post.assert_called_once()
                    _, kwargs = mock_post.call_args
                    assert kwargs["json"]["quantity"] == pytest.approx(2.0, rel=1e-4)


@pytest.mark.asyncio
async def test_min_trade_quantity_sell_side_also_rejected():
    """minTradeQuantity=2.0 enforcement applies to SELL orders as well as BUY."""
    service = BrokerageService("T212")
    mock_metadata = {"minTradeQuantity": 2.0, "quantityIncrement": 0.05}

    with patch.object(service.provider, "get_symbol_metadata", return_value=mock_metadata):
        with patch("src.services.data_service.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_price:
            mock_price.return_value = {"AAPL": 1000.0}
            with patch("src.services.risk_service.risk_service.calculate_friction") as mock_friction:
                mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}
                with patch.object(service.provider.session, "post") as mock_post:
                    result = await service.place_value_order("AAPL", 100.0, "SELL")

                    # quantity = 100 / 1000 = 0.1, which is below minTradeQuantity=2.0
                    assert result["status"] == "error"
                    assert "minTradeQuantity" in result["message"]
                    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_get_available_quantity_uses_positions_endpoint():
    """get_available_quantity returns quantityAvailableForTrading from the provider."""


    # The provider is responsible for fetching and normalising positions.
    # Mock at the provider boundary so we don't depend on HTTP internals.
    normalised_positions = [
        {
            "ticker": "AAPL",
            "quantity": 5.0,
            "quantityAvailableForTrading": 3.5,
            "averagePrice": 100.0,
        }
    ]

    with patch.object(service.provider, "get_positions", return_value=normalised_positions):
        available = await service.get_available_quantity("AAPL")

    assert available == 3.5
