import unittest
import numpy as np
import pandas as pd
from src.services.arbitrage_service import ArbitrageService

class TestArbitrageMath(unittest.TestCase):
    def setUp(self):
        self.arbitrage = ArbitrageService()

    def test_z_score_calculation(self):
        """
        Test that Z-score is calculated correctly.
        Z = (Current Spread - Mean Spread) / Std Dev Spread
        """
        current_spread = 10.0
        mean_spread = 5.0
        std_spread = 2.0
        
        expected_z = (10.0 - 5.0) / 2.0  # 2.5
        calculated_z = self.arbitrage.calculate_z_score(current_spread, mean_spread, std_spread)
        
        self.assertEqual(calculated_z, expected_z)

    def test_spread_calculation(self):
        """
        Spread = Price A - (Hedge Ratio * Price B)
        """
        price_a = 150.0
        price_b = 100.0
        hedge_ratio = 1.2
        
        expected_spread = 150.0 - (1.2 * 100.0)  # 30.0
        calculated_spread = self.arbitrage.calculate_spread(price_a, price_b, hedge_ratio)
        
        self.assertEqual(calculated_spread, expected_spread)

    def test_cointegration_parameters(self):
        """
        Verify that we can calculate hedge ratio, mean, and std from historical data.
        """
        # Create dummy cointegrated-like data
        np.random.seed(42)
        price_b = np.linspace(100, 110, 100) + np.random.normal(0, 1, 100)
        price_a = 1.5 * price_b + 5.0 + np.random.normal(0, 1, 100)
        
        df = pd.DataFrame({'asset_a': price_a, 'asset_b': price_b})
        
        params = self.arbitrage.update_pair_parameters(df)
        
        self.assertIn('hedge_ratio', params)
        self.assertIn('mean_spread', params)
        self.assertIn('std_spread', params)
        self.assertGreater(params['hedge_ratio'], 1.0) # Roughly 1.5

if __name__ == '__main__':
    unittest.main()
