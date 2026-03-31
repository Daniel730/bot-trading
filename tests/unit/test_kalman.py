import numpy as np
import pytest
from src.services.kalman_service import KalmanFilter

def test_kalman_convergence():
    """
    Tests if the Kalman Filter can track a known drifting beta.
    """
    kf = KalmanFilter(delta=1e-4, R=0.01)
    
    # Generate synthetic data where Ticker A = 1.5 * Ticker B + 0.5 (with noise)
    # Then it drifts to Ticker A = 1.8 * Ticker B + 0.5
    np.random.seed(42)
    n_samples = 100
    ticker_b = np.random.normal(100, 5, n_samples)
    
    # Initial regime (beta=1.5)
    ticker_a = 1.5 * ticker_b[:50] + 0.5 + np.random.normal(0, 0.1, 50)
    # Drifted regime (beta=1.8)
    ticker_a = np.append(ticker_a, 1.8 * ticker_b[50:] + 0.5 + np.random.normal(0, 0.1, 50))
    
    betas = []
    alphas = []
    
    for a, b in zip(ticker_a, ticker_b):
        beta, alpha, _ = kf.update(a, b)
        betas.append(beta)
        alphas.append(alpha)
    
    # Verify initial convergence (after ~20 samples)
    assert 1.45 < betas[40] < 1.55
    # Verify drift tracking (at the end)
    assert 1.75 < betas[-1] < 1.85
    # Verify alpha tracking
    assert 0.4 < alphas[-1] < 0.6

def test_kalman_zscore_smoothing():
    """
    Verifies that the Z-score remains bounded during normal drift.
    """
    kf = KalmanFilter(delta=1e-4, R=0.01)
    np.random.seed(42)
    n_samples = 50
    ticker_b = np.linspace(100, 110, n_samples)
    ticker_a = 1.5 * ticker_b + 0.5 + np.random.normal(0, 0.05, n_samples)
    
    z_scores = []
    for a, b in zip(ticker_a, ticker_b):
        _, _, z = kf.update(a, b)
        z_scores.append(z)
        
    # After convergence, Z-scores for a matching spread should mostly be within 2 standard deviations
    stable_zs = z_scores[20:]
    assert all(abs(z) < 3.0 for z in stable_zs)
