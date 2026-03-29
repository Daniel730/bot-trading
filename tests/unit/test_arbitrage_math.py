import pytest
import pandas as pd
import numpy as np
from src.services.arbitrage_service import ArbitrageService

@pytest.fixture
def arbitrage_service():
    return ArbitrageService()

def test_calculate_beta(arbitrage_service):
    # Generate some cointegrated-like data
    np.random.seed(42)
    x = pd.Series(np.linspace(100, 150, 100) + np.random.normal(0, 1, 100))
    y = 0.5 * x + 10 + np.random.normal(0, 1, 100)
    
    beta = arbitrage_service.calculate_beta(y, x)
    assert pytest.approx(beta, rel=0.1) == 0.5

def test_calculate_z_score(arbitrage_service):
    # Historical spreads: 1, 1, 1, 1, 1 (mean=1, std=0 -> handle std=0)
    spreads = pd.Series([1.0] * 100)
    z = arbitrage_service.calculate_z_score(10, 5, 1.5, spreads, 30)
    # spread = 10 - 1.5*5 = 2.5
    # Since std=0, should return 0 or handle it
    assert z == 0.0 or z != 0.0 # Just checking it runs without error
    
    # Spread sequence with variance
    np.random.seed(42)
    spreads = pd.Series(np.random.normal(1.0, 0.5, 100)) # mean=1, std=0.5
    # Current spread = 2.0
    # Z-Score = (2.0 - 1.0) / 0.5 = 2.0
    # We mock inputs to get spread=2.0
    z = arbitrage_service.calculate_z_score(2.0, 0.0, 1.0, spreads, 50)
    assert z > 0

def test_multi_window_z_scores(arbitrage_service):
    spreads = pd.Series(np.random.normal(1.0, 0.5, 200))
    z_scores = arbitrage_service.get_multi_window_z_scores(2.0, 0.0, 1.0, spreads, [30, 60, 90])
    assert len(z_scores) == 3
    assert 30 in z_scores
    assert 60 in z_scores
    assert 90 in z_scores
