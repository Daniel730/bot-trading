import pytest
import numpy as np
import pandas as pd
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.agents.portfolio_manager_agent import portfolio_manager_agent

def test_sortino_ratio_calculation():
    """
    Test G6: Verificação do cálculo do Sortino Ratio.
    Deve ignorar volatilidade positiva e penalizar estritamente a negativa.
    """
    # Create synthetic returns
    # Asset A: High positive volatility, zero negative volatility
    # Asset B: Zero positive volatility, high negative volatility
    
    dates = pd.date_range(start="2024-01-01", periods=10)
    
    # Positive only returns (Sortino should be high)
    returns_pos = pd.DataFrame({"A": [0.01, 0.05, 0.00, 0.02, 0.08, 0.01, 0.03, 0.04, 0.00, 0.02]}, index=dates)
    weights = np.array([1.0])
    
    # Calculate Sortino (RFR 0 for simplicity)
    sortino_pos = portfolio_manager_agent.calculate_sortino_ratio(weights, returns_pos, risk_free_rate=0.0)
    
    # Negative only returns (Sortino should be negative)
    returns_neg = pd.DataFrame({"B": [-0.01, -0.05, 0.00, -0.02, -0.08, -0.01, -0.03, -0.04, 0.00, -0.02]}, index=dates)
    sortino_neg = portfolio_manager_agent.calculate_sortino_ratio(weights, returns_neg, risk_free_rate=0.0)
    
    assert sortino_pos > 0
    assert sortino_neg < 0
    assert sortino_pos > sortino_neg

@pytest.mark.asyncio
async def test_portfolio_optimization_constraints():
    """
    Test G6: Verificação das restrições do MVO (Sum=1.0, Max=20%).
    """
    tickers = ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "BRK.B"]
    
    # Mock historical data to return random returns
    mock_data = pd.DataFrame(
        np.random.normal(0.001, 0.02, (252, len(tickers))),
        columns=tickers,
        index=pd.date_range("2023-01-01", periods=252)
    )
    
    with patch('src.services.data_service.DataService.get_historical_data', return_value=mock_data), \
         patch('src.services.persistence_service.persistence_service.update_optimized_allocation', new_callable=AsyncMock):
        
        weights = await portfolio_manager_agent.optimize_portfolio(tickers)
        
        # Check sum logic
        total_weight = sum(weights.values())
        assert pytest.approx(total_weight, 0.001) == 1.0
        
        # Check individual constraint (Max 20%)
        for t, w in weights.items():
            assert w <= 0.200001 # Tolerance for float
            assert w >= -0.000001
