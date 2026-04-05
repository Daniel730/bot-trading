import pytest
import pandas as pd
import numpy as np
from src.services.risk_service import PortfolioOptimizer

def test_covariance_matrix_calculation():
    optimizer = PortfolioOptimizer()
    
    # Mock return data
    data = {
        'AAPL': [0.01, 0.02, -0.01, 0.015, 0.03],
        'MSFT': [0.012, 0.018, -0.008, 0.014, 0.028],
        'GOLD': [-0.005, -0.01, 0.02, -0.005, -0.015] # Uncorrelated/Negative
    }
    df = pd.DataFrame(data)
    
    cov_matrix = optimizer.calculate_covariance(df)
    
    # AAPL and MSFT should have high positive covariance
    assert cov_matrix.loc['AAPL', 'MSFT'] > 0
    # GOLD should have negative or low covariance with AAPL
    assert cov_matrix.loc['AAPL', 'GOLD'] < 0
