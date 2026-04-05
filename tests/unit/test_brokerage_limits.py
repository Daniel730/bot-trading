import pytest
from unittest.mock import patch, MagicMock
from src.services.brokerage_service import BrokerageService

def test_quantity_rounding_and_limits():
    """
    T011: Verifies that place_value_order enforces minTradeQuantity 
    and rounds to quantityIncrement.
    """
    service = BrokerageService()
    
    # Mock metadata: min 0.1, increment 0.05
    mock_metadata = {
        "minTradeQuantity": 0.1,
        "quantityIncrement": 0.05
    }
    
    # Mock data_service price: $100
    mock_prices = {"AAPL": 100.0}
    
    with patch.object(service, 'get_symbol_metadata', return_value=mock_metadata):
        with patch('src.services.data_service.data_service.get_latest_price', return_value=mock_prices):
            # Test 1: Amount $12 -> Qty 0.12 -> Should round to 0.10 (nearest 0.05)
            # Actually, rounding 0.12 to nearest 0.05 is 0.10.
            # Amount $17 -> Qty 0.17 -> Should round to 0.15
            
            with patch.object(service, 'place_market_order') as mock_place:
                # Mock success response
                mock_place.return_value = {"status": "filled"}
                
                # Amount $172, Price $100 -> Qty 1.72 shares. 
                # Friction: 0.5 / 172 = 0.0029 (0.29%) < 1.5%. ACCEPTABLE.
                # Nearest 0.05 increment to 1.72 is 1.70.
                
                result = service.place_value_order("AAPL", 172.0, "BUY")
                if result.get("status") == "error":
                    print(f"DEBUG: {result['message']}")
                mock_place.assert_called_once()
                args, _ = mock_place.call_args
                # args[1] is quantity
                assert args[1] == 1.70
                
            # Test 2: Amount $100, Price $1000 -> Qty 0.1 -> Should be rejected (min 0.2)
            # Friction: 0.5 / 100 = 0.5% (Acceptable < 1.5%)
            mock_metadata["minTradeQuantity"] = 0.2
            mock_prices["AAPL"] = 1000.0
            with patch.object(service, 'place_market_order') as mock_place:
                result = service.place_value_order("AAPL", 100.0, "BUY")
                if result.get("status") != "error":
                    print(f"DEBUG: result {result}")
                assert result["status"] == "error"
                assert "minTradeQuantity" in result["message"]
                mock_place.assert_not_called()

if __name__ == "__main__":
    test_quantity_rounding_and_limits()
