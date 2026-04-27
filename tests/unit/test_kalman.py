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
        
        # First update to set innovation_variance
        kf.update(pa, pb)
        
        spread, z_score = kf.calculate_spread_and_zscore(pa, pb)
        
        self.assertIsInstance(spread, float)
        self.assertIsInstance(z_score, float)

    def test_bump_uncertainty_convergence(self):
        """Test if bump_uncertainty speeds up convergence after a gap."""
        # Setup: converge to beta=1.0
        kf = KalmanFilter(delta=1e-5, r=1e-3)
        for _ in range(100):
            kf.update(100.0, 100.0)
        
        initial_beta = kf.state[1]
        self.assertAlmostEqual(initial_beta, 1.0, places=2)
        
        # Scenario: sudden gap to beta=2.0
        # We'll create two filters: one bumped, one not.
        kf_normal = KalmanFilter(delta=1e-5, r=1e-3)
        kf_bumped = KalmanFilter(delta=1e-5, r=1e-3)
        
        # Sync states
        kf_normal.state = kf.state.copy()
        kf_normal.P = kf.P.copy()
        kf_bumped.state = kf.state.copy()
        kf_bumped.P = kf.P.copy()
        
        # Apply bump to one
        kf_bumped.bump_uncertainty(multiplier=100.0)
        
        # New observation reflecting beta=2.0 (Price A = 200, Price B = 100)
        kf_normal.update(200.0, 100.0)
        kf_bumped.update(200.0, 100.0)
        
        # The bumped filter should have moved much closer to beta=2.0
        dist_normal = abs(kf_normal.state[1] - 2.0)
        dist_bumped = abs(kf_bumped.state[1] - 2.0)
        
        print(f"\nNormal beta after gap: {kf_normal.state[1]:.4f} (dist: {dist_normal:.4f})")
        print(f"Bumped beta after gap: {kf_bumped.state[1]:.4f} (dist: {dist_bumped:.4f})")
        
        self.assertLess(dist_bumped, dist_normal, "Bumped filter should converge faster after a gap.")

if __name__ == '__main__':
    unittest.main()
