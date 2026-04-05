import pytest
from src.services.brokerage_service import BrokerageService
from src.services.risk_service import risk_service
from unittest.mock import patch, MagicMock

def test_value_order_flow_success():
    brokerage = BrokerageService()
    
    with patch('src.services.data_service.data_service.get_latest_price') as mock_price:
        mock_price.return_value = {"AAPL": 150.0}
        
        with patch.object(brokerage, 'place_market_order') as mock_market:
            mock_market.return_value = {"status": "success", "orderId": "12345"}
            
            # $15 of AAPL @ $150 = 0.1 shares
            result = brokerage.place_value_order("AAPL", 15.0, "BUY")
            
            assert result['status'] == "success"
            mock_market.assert_called_once_with("AAPL", 0.1, "BUY")

def test_value_order_fee_rejection():
    # We test the logic in monitor.py integration via risk_service
    # If $0.50 trade is attempted, it should be rejected by risk_service
    
    amount = 0.50
    check = risk_service.is_trade_allowed(amount, 0.01) # 1% friction
    assert check['allowed'] == False
    assert "below minimum" in check['reason']

    # High friction case
    amount = 10.0
    check = risk_service.is_trade_allowed(amount, 0.05) # 5% friction
    assert check['allowed'] == False
    assert "exceeds limit" in check['reason']
