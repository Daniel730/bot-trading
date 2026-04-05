import pytest
import pandas as pd
import numpy as np
import statsmodels.api as sm
from src.services.arbitrage_service import ArbitrageService

def test_ols_intercept_requirement():
    """
    T012: Verifies that the cointegration test handles series with a constant offset.
    With the fix, the hedge ratio should be unbiased (~2.0) despite the offset.
    """
    np.random.seed(42)
    n = 200
    s2 = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    
    # s1 is 2*s2 + a large constant offset + some stationary noise
    constant_offset = 50.0
    hedge_ratio_true = 2.0
    noise = np.random.randn(n) * 0.1
    s1 = hedge_ratio_true * s2 + constant_offset + noise
    
    is_coint, p_val, hedge_ratio = ArbitrageService.check_cointegration(s1, s2)
    
    print(f"P-Value: {p_val}, Calculated Hedge Ratio: {hedge_ratio}")
    
    # We expect the hedge ratio to be close to 2.0. 
    # Without the fix, it was ~2.5.
    assert abs(hedge_ratio - 2.0) < 0.05, f"Hedge ratio {hedge_ratio} is biased. Expected ~2.0"
    assert is_coint is True, f"Should be cointegrated. P-value: {p_val}"

def test_spread_metrics_intercept():
    """
    Verifies that get_spread_metrics returns the intercept and zero-mean spread.
    """
    np.random.seed(42)
    n = 100
    s2 = pd.Series(np.random.randn(n) + 100)
    s1 = 2.0 * s2 + 50.0 + np.random.randn(n) * 0.1
    
    metrics = ArbitrageService.get_spread_metrics(s1, s2, 2.0)
    
    assert "intercept" in metrics
    assert abs(metrics["intercept"] - 50.0) < 1.0
    # Mean spread should be ~0 after intercept subtraction
    assert abs(metrics["mean"]) < 0.01

if __name__ == "__main__":
    test_ols_intercept_requirement()
    test_spread_metrics_intercept()
