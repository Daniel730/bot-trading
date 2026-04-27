import sys
import os
import unittest
import numpy as np

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.services.kalman_service import KalmanFilter

class TestKalmanFilter(unittest.TestCase):
    def test_convergence_on_static_data(self):
        """Test if beta converges to the true ratio in static data."""
        true_beta = 1.5
        true_alpha = 0.5
        
        # Slightly higher delta to allow faster intercept movement if needed
        kf = KalmanFilter(delta=1e-4, r=1e-4)
        
        # Initial state is [0.0, 1.0]
        # Generate 500 points
        np.random.seed(42)
        price_b = np.linspace(100, 200, 500)
        price_a = true_beta * price_b + true_alpha + np.random.normal(0, 0.01, 500)
        
        for pa, pb in zip(price_a, price_b):
            kf.update(pa, pb)
            
        alpha, beta = kf.state
        
        # Should be close to 1.5 and 0.5
        self.assertAlmostEqual(beta, true_beta, places=2)
        # Intercept is harder to estimate precisely in pair trading
        self.assertAlmostEqual(alpha, true_alpha, delta=0.5) 

    def test_tracking_drifting_beta(self):
        """Test if the filter tracks a changing hedge ratio."""
        kf = KalmanFilter(delta=1e-3, r=1e-4)
        
        np.random.seed(42)
        n_points = 200
        price_b = np.linspace(100, 150, n_points)
        
        # Beta drifts from 1.0 to 2.0
        true_betas = np.linspace(1.0, 2.0, n_points)
        price_a = true_betas * price_b + np.random.normal(0, 0.05, n_points)
        
        for pa, pb in zip(price_a, price_b):
            kf.update(pa, pb)
            
        # Final beta should be close to 2.0
        alpha, beta = kf.state
        self.assertAlmostEqual(beta, 2.0, places=1)

    def test_zscore_generation(self):
        """Test spread and z-score calculation."""
        kf = KalmanFilter(delta=1e-5, r=1e-3)
        pa, pb = 150.5, 100.0
        
        # Initial state [0.0, 1.0]
        # Expected spread = 150.5 - (1.0 * 100.0 + 0.0) = 50.5
        
        # update() now returns (state, innovation_variance, z_score, spread)
        # where z_score and spread are calculated BEFORE the update (using prior state).
        state, inv_var, z_score, spread = kf.update(pa, pb)
        
        self.assertAlmostEqual(spread, 50.5)
        self.assertIsInstance(z_score, float)
        self.assertTrue(z_score > 0)
        
        # Since the filter was at [0,1], the spread should be 50.5.
        # Innovation variance depends on P (initially 10*I) and R (1e-3).
        # S = H*P*H^T + R = [1, 100] * [[10,0],[0,10]] * [1, 100]^T + 0.001
        # S = (10 + 10*10000) + 0.001 = 100010.001
        # z = 50.5 / sqrt(100010.001) approx 50.5 / 316.24 approx 0.159
        self.assertAlmostEqual(z_score, 50.5 / np.sqrt(inv_var))

        
if __name__ == '__main__':
    unittest.main()
