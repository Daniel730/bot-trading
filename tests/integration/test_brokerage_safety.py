import pytest
from unittest.mock import MagicMock, patch
from src.services.brokerage_service import BrokerageService

def test_pending_orders_value_fallback():
    """
    Verifies that get_pending_orders_value uses data_service fallback
    when the brokerage returns a price of 0.0 for a pending order.
    """
    service = BrokerageService()
    
    # Mock pending orders: one order with 0.0 price
    mock_orders = [
        {
            "ticker": "AAPL_US_EQ",
            "quantity": 10.0,
            "price": 0.0
        }
    ]
    
    # Mock data_service to return a price of 150.0
    mock_prices = {"AAPL_US_EQ": 150.0}
    
    with patch.object(service, 'get_pending_orders', return_value=mock_orders):
        with patch('src.services.data_service.data_service.get_latest_price', return_value=mock_prices):
            total_value = service.get_pending_orders_value()
            
            # Expected value: 10.0 * 150.0 = 1500.0
            # If fallback fails, it would be 0.0
            assert total_value == 1500.0, f"Expected 1500.0, but got {total_value}"

if __name__ == "__main__":
    test_pending_orders_value_fallback()
