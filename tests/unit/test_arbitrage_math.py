import pytest
import pandas as pd
import numpy as np
from src.services.arbitrage_service import arbitrage_service
from src.services.risk_service import risk_service

def test_calculate_zscore():
    # Mean spread 0, std 1
    z = arbitrage_service.calculate_zscore(10, 5, 2, 0, 1) # (10 - 2*5 - 0) / 1 = 0
    assert z == 0
    
    z = arbitrage_service.calculate_zscore(12, 5, 2, 0, 1) # (12 - 2*5 - 0) / 1 = 2
    assert z == 2

def test_kelly_sizing():
    # Confidence 0.6, win/loss 1.0 -> kelly_f = 0.6 - 0.4 = 0.2
    # Fractional (0.25) -> 0.2 * 0.25 = 0.05
    # Limit by MAX_RISK_PER_TRADE (0.02)
    size = risk_service.calculate_kelly_size(0.6, 1.0)
    assert size == 0.02

def test_cointegration_logic():
    # Create two cointegrated series
    np.random.seed(42)
    x = np.random.normal(0, 1, 100).cumsum()
    y = x + np.random.normal(0, 0.1, 100) # Highly cointegrated
    
    is_coint, p_val, hedge = arbitrage_service.check_cointegration(pd.Series(y), pd.Series(x))
    assert is_coint == True
    assert p_val < 0.05
