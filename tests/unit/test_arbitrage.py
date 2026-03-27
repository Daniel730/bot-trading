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

    def test_rebalance_logic_capped(self):
        """
        Verify rebalance logic with risk capping.
        """
        current_positions = {'AAPL': 0.0, 'MSFT': 0.0}
        current_prices = {'AAPL': 150.0, 'MSFT': 250.0}
        target_weights = {'AAPL': 0.5, 'MSFT': 0.5}
        free_cash = 1000.0
        max_allocation_pct = 10.0 # 10% of 1000 = 100
        
        # Target value for AAPL is 500, but capped at 100.
        # Order for AAPL should be 100 / 150 = 0.666667 shares
        orders = self.arbitrage.calculate_rebalance_orders(
            current_positions, current_prices, target_weights, free_cash, max_allocation_pct
        )
        
        self.assertEqual(orders['AAPL'], round(100.0 / 150.0, 6))
        self.assertEqual(orders['MSFT'], round(100.0 / 250.0, 6))

    def test_rebalance_logic_uncapped(self):
        """
        Verify rebalance logic without risk capping.
        """
        current_positions = {'AAPL': 0.0}
        current_prices = {'AAPL': 100.0}
        target_weights = {'AAPL': 0.1}
        free_cash = 1000.0
        max_allocation_pct = 20.0 # 20% of 1000 = 200
        
        # Target value for AAPL is 1000 * 0.1 = 100.
        # Max trade is 200. No capping.
        # Order should be 100 / 100 = 1.0 share.
        orders = self.arbitrage.calculate_rebalance_orders(
            current_positions, current_prices, target_weights, free_cash, max_allocation_pct
        )
        
        self.assertEqual(orders['AAPL'], 1.0)
