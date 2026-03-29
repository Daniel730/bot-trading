import unittest
import numpy as np
import pandas as pd
from src.services.arbitrage_service import ArbitrageService
from src.models.arbitrage_models import OrderType

class TestArbitrageMath(unittest.TestCase):
    def setUp(self):
        self.arbitrage = ArbitrageService()

    def test_calculate_hedge_ratio(self):
        """
        Test that hedge ratio is calculated correctly using OLS.
        """
        # Create a perfectly cointegrated pair
        data_b = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
        # data_a = 1.5 * data_b + 5
        data_a = pd.Series([20.0, 21.5, 23.0, 24.5, 26.0])
        
        expected_beta = 1.5
        calculated_beta = self.arbitrage.calculate_hedge_ratio(data_a, data_b)
        
        self.assertAlmostEqual(calculated_beta, expected_beta, places=5)

    def test_calculate_spread(self):
        """
        Spread = Price A - (Beta * Price B)
        """
        data_a = pd.Series([150.0, 155.0])
        data_b = pd.Series([100.0, 102.0])
        beta = 1.2
        
        expected_spread = pd.Series([150.0 - (1.2 * 100.0), 155.0 - (1.2 * 102.0)])
        calculated_spread = self.arbitrage.calculate_spread(data_a, data_b, beta)
        
        pd.testing.assert_series_equal(calculated_spread, expected_spread)

    def test_calculate_z_score(self):
        """
        Test Z-score calculation on a spread series.
        """
        spread = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
        window = 3
        
        # For window=3, first two values will be NaN
        # 3rd value: mean=[10,11,12]=11, std=1.0. Z=(12-11)/1=1.0
        # 4th value: mean=[11,12,13]=12, std=1.0. Z=(13-12)/1=1.0
        # 5th value: mean=[12,13,14]=13, std=1.0. Z=(14-13)/1=1.0
        
        calculated_z = self.arbitrage.calculate_z_score(spread, window)
        
        self.assertTrue(np.isnan(calculated_z.iloc[0]))
        self.assertTrue(np.isnan(calculated_z.iloc[1]))
        self.assertAlmostEqual(calculated_z.iloc[2], 1.0)
        self.assertAlmostEqual(calculated_z.iloc[3], 1.0)
        self.assertAlmostEqual(calculated_z.iloc[4], 1.0)

    def test_calculate_rebalance_orders(self):
        """
        Verify rebalance order generation.
        """
        ticker_a = "KO"
        ticker_b = "PEP"
        beta = 1.1
        current_price_a = 60.0
        current_price_b = 170.0
        target_value = 1000.0
        
        # Case 1: Z > 2.5 -> Sell A, Buy B
        z_score = 3.0
        orders = self.arbitrage.calculate_rebalance_orders(
            ticker_a, ticker_b, beta, current_price_a, current_price_b, target_value, z_score
        )
        
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0]['ticker'], "KO")
        self.assertEqual(orders[0]['quantity'], -1.0)
        self.assertEqual(orders[1]['ticker'], "PEP")
        self.assertEqual(orders[1]['quantity'], 1.1)

        # Case 2: Z < -2.5 -> Buy A, Sell B
        z_score = -3.0
        orders = self.arbitrage.calculate_rebalance_orders(
            ticker_a, ticker_b, beta, current_price_a, current_price_b, target_value, z_score
        )
        
        self.assertEqual(len(orders), 2)
        # Sell PEP first, then Buy KO
        self.assertEqual(orders[0]['ticker'], "PEP")
        self.assertEqual(orders[0]['quantity'], -1.1)
        self.assertEqual(orders[1]['ticker'], "KO")
        self.assertEqual(orders[1]['quantity'], 1.0)

        # Case 3: Neutral Z -> No orders
        z_score = 0.0
        orders = self.arbitrage.calculate_rebalance_orders(
            ticker_a, ticker_b, beta, current_price_a, current_price_b, target_value, z_score
        )
        self.assertEqual(len(orders), 0)

    def test_calculate_paper_trade(self):
        """
        Verify paper trade ledger and balance calculations.
        """
        ticker = "KO"
        quantity = 10.0
        price = 60.0
        order_type = OrderType.BUY
        current_balance = 1000.0
        
        ledger, new_balance = self.arbitrage.calculate_paper_trade(
            ticker, quantity, price, order_type, current_balance
        )
        
        self.assertEqual(ledger['ticker'], "KO")
        self.assertEqual(ledger['quantity'], 10.0)
        self.assertEqual(new_balance, 400.0) # 1000 - (10 * 60)
        
        # Test Sell
        ledger, new_balance = self.arbitrage.calculate_paper_trade(
            ticker, -5.0, 65.0, OrderType.SELL, 400.0
        )
        self.assertEqual(new_balance, 725.0) # 400 + (5 * 65)

if __name__ == '__main__':
    unittest.main()
