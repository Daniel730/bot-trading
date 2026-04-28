import pytest
import sys
import os
import numpy as np

# Ensure src is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from unittest.mock import patch, MagicMock, AsyncMock
from src.services.performance_service import PerformanceService

@pytest.mark.asyncio
async def test_dynamic_sharpe_impact():
    """
    Test F4: Verify that fetching a high dynamic risk-free rate (^TNX)
    lowers the Sharpe Ratio appropriately.
    """
    ps = PerformanceService()
    
    # Mock data: 2% profit over 30 days
    # daily_returns ~ 0.00066 (2% / 30)
    daily_pnl = {f"2026-04-{i:02d}": 1.33 for i in range(1, 31)} # 1.33 * 30 ~ 40 USD profit on 2000 capital
    
    # Case 1: High Risk-Free Rate (5%)
    with patch('src.services.persistence_service.persistence_service.get_daily_returns', return_value=daily_pnl), \
         patch('src.services.performance_service.redis_service.get_json', return_value=None), \
         patch('src.services.performance_service.redis_service.set_json', return_value=None), \
         patch('yfinance.Ticker') as mock_ticker:
        
        mock_info = MagicMock()
        mock_info.info = {"previousClose": 5.0} # 5% Yield
        mock_ticker.return_value = mock_info
        
        metrics_high = await ps.get_portfolio_metrics()
        sharpe_high = metrics_high['sharpe_ratio']
        
        # Case 2: Low Risk-Free Rate (1%)
        mock_info.info = {"previousClose": 1.0} # 1% Yield
        metrics_low = await ps.get_portfolio_metrics()
        sharpe_low = metrics_low['sharpe_ratio']
        
        # Assertion: High RFR must result in a lower Sharpe Ratio for the same profit
        assert sharpe_high < sharpe_low, f"Sharpe high ({sharpe_high}) should be less than Sharpe low ({sharpe_low})"
        assert ps.risk_free_rate == 0.01, "Risk-free rate was not updated correctly in the second run."

@pytest.mark.asyncio
async def test_risk_free_fetch_fallback():
    """
    Test F4: Verify fallback to 2% if yfinance fails.
    """
    ps = PerformanceService()
    with patch('yfinance.Ticker', side_effect=Exception("API Error")):
        rfr = await ps.get_dynamic_risk_free_rate()
        assert rfr == 0.02, "PerformanceService should fallback to 2% (0.02) on API failure."
