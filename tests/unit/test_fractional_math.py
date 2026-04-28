import pytest
from src.services.brokerage_service import BrokerageService
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_fractional_quantity_precision():
    service = BrokerageService()
    
    # Test high precision rounding (6 decimal places)
    # 10 / 173.50 = 0.05763688... -> 0.057637
    amount = 10.0
    price = 173.50
    expected_qty = round(amount / price, 6)
    
    assert expected_qty == 0.057637
    
    with patch('src.services.data_service.data_service.get_latest_price', new_callable=AsyncMock) as mock_price:
        mock_price.return_value = {"AAPL": 173.50}
        with patch('src.services.risk_service.risk_service.calculate_friction') as mock_friction:
            mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}
            with patch.object(service, 'place_market_order', new_callable=AsyncMock) as mock_order:
                mock_order.return_value = {"status": "success"}
                await service.place_value_order("AAPL", 10.0, "BUY")
            
                # Verify the quantity sent to place_market_order is rounded to 6 places
                args, _ = mock_order.call_args
                assert args[0] == "AAPL"
                assert args[1] == 0.057637
                assert args[2] == "BUY"

@pytest.mark.asyncio
async def test_micro_budget_quantity():
    service = BrokerageService()
    # $1 / $3500 (AMZN style) = 0.0002857... -> 0.000286
    amount = 1.0
    price = 3500.0
    
    with patch('src.services.data_service.data_service.get_latest_price', new_callable=AsyncMock) as mock_price:
        mock_price.return_value = {"AMZN": 3500.0}
        with patch('src.services.risk_service.risk_service.calculate_friction') as mock_friction:
            mock_friction.return_value = {"is_acceptable": True, "friction_pct": 0.001}
            with patch.object(service, 'place_market_order', new_callable=AsyncMock) as mock_order:
                mock_order.return_value = {"status": "success"}
                await service.place_value_order("AMZN", 1.0, "BUY")
                args, _ = mock_order.call_args
                assert args[1] == 0.000286
