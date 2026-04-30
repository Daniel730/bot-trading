import pytest
from src.services.brokerage_service import BrokerageService
from unittest.mock import patch, AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_fractional_quantity_precision():
    service = BrokerageService("T212")

    # Trading212 rejects six-decimal equity quantities for instruments such as DUK.
    # When metadata omits quantityIncrement, use the seed script's 0.01-share default.
    amount = 10.0
    price = 173.50
    
    with patch('src.services.data_service.data_service.get_latest_price_async', new_callable=AsyncMock) as mock_price:
        mock_price.return_value = {"AAPL": 173.50}
        with patch('src.services.risk_service.risk_service.calculate_friction') as mock_friction:
            mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}
            with patch.object(service.provider, "get_symbol_metadata", return_value={}):
                with patch.object(service.provider.session, 'post') as mock_post:
                    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"orderId": "success"})
                    await service.place_value_order("AAPL", amount, "BUY")

                    _, kwargs = mock_post.call_args
                    assert kwargs['json']['ticker'] == "AAPL_US_EQ"
                    assert kwargs['json']['quantity'] == 0.05

@pytest.mark.asyncio
async def test_micro_budget_quantity():
    service = BrokerageService("T212")
    # With T212's 0.01-share fallback, tiny budgets for high-priced names
    # should be rejected before sending a broker payload.
    amount = 1.0
    price = 3500.0
    
    with patch('src.services.data_service.data_service.get_latest_price_async', new_callable=AsyncMock) as mock_price:
        mock_price.return_value = {"AMZN": 3500.0}
        with patch('src.services.risk_service.risk_service.calculate_friction') as mock_friction:
            mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}
            with patch.object(service.provider, "get_symbol_metadata", return_value={}):
                with patch.object(service.provider.session, 'post') as mock_post:
                    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"orderId": "success"})
                    result = await service.place_value_order("AMZN", amount, "BUY")
                    assert result["status"] == "error"
                    assert "rounds to zero" in result["message"]
                    mock_post.assert_not_called()
