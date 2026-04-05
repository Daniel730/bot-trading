import pytest
from unittest.mock import patch, MagicMock
from src.services.risk_service import RiskService

@pytest.mark.asyncio
async def test_regional_hedging_compliance():
    """
    T016: Verifies that RiskService.check_hedging provides UCITS fallbacks
    when the environment indicates a regulated region (e.g., EU).
    """
    risk_service = RiskService()
    
    # Mock portfolio with SPY
    mock_portfolio = [{"ticker": "SPY_US_EQ", "quantity": 10, "averagePrice": 500}]
    
    with patch('src.services.brokerage_service.brokerage_service.get_portfolio', return_value=mock_portfolio):
        # Patch src.config.settings directly
        with patch('src.config.settings') as mock_settings:
            # Test 1: Standard US mode
            mock_settings.REGION = 'US'
            res = await risk_service.check_hedging(hedging_state="DEFCON_1")
            assert res["hedges"][0]["hedge"] == "SH"
            
            # Test 2: EU mode -> Should return UCITS equivalent
            mock_settings.REGION = 'EU'
            res = await risk_service.check_hedging(hedging_state="DEFCON_1")
            print(f"DEBUG: Region in res: {res.get('region')}, Hedges: {res.get('hedges')}")
            # XSPS.L is a common UCITS Inverse S&P 500 ETF
            assert res["hedges"][0]["hedge"] == "XSPS.L"

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_regional_hedging_compliance())
