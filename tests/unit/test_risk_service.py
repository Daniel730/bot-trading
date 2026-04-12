import pytest
from unittest.mock import AsyncMock, patch
from src.services.risk_service import risk_service
import asyncio

@pytest.mark.asyncio
async def test_check_hedging_fixed():
    """
    T-01: Verify fix for missing await for get_portfolio() in check_hedging().
    """
    mock_portfolio = [{"ticker": "AAPL", "quantity": 10, "averagePrice": 150}]
    
    with patch("src.services.brokerage_service.brokerage_service.get_portfolio", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_portfolio
        
        # This should NOT raise TypeError if it's awaited properly.
        result = await risk_service.check_hedging("DEFCON_1")
        assert result["status"] == "DEFCON_1"
        assert len(result["hedges"]) == 0 # AAPL not in map
        mock_get.assert_called_once()
