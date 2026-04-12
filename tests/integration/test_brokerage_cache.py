import unittest
import time
from unittest.mock import patch, MagicMock
from src.services.brokerage_service import BrokerageService
from src.config import settings

class TestBrokerageCache(unittest.TestCase):
    def setUp(self):
        self.patcher_key = patch.object(settings, 'T212_API_KEY', 'test_key')
        self.patcher_mode = patch.object(settings, 'TRADING_212_MODE', 'demo')
        self.patcher_key.start()
        self.patcher_mode.start()
        self.service = BrokerageService()

    def tearDown(self):
        self.patcher_key.stop()
        self.patcher_mode.stop()

    @patch('src.services.brokerage_service.requests.get')
    def test_get_portfolio_caching(self, mock_get):
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"ticker": "AAPL", "quantity": 1}]
        mock_get.return_value = mock_response

        # First call - should trigger request
        res1 = self.service.get_portfolio()
        self.assertEqual(len(res1), 1)
        mock_get.assert_called_once()

        # Second call immediately - should use cache
        res2 = self.service.get_portfolio()
        self.assertEqual(res1, res2)
        mock_get.assert_called_once() # Still once

    @patch('src.services.brokerage_service.requests.get')
    def test_get_pending_orders_caching(self, mock_get):
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"ticker": "MSFT", "quantity": 5}]
        mock_get.return_value = mock_response

        # First call - should trigger request
        res1 = self.service.get_pending_orders()
        self.assertEqual(len(res1), 1)
        mock_get.assert_called_once()

        # Second call immediately - should use cache
        res2 = self.service.get_pending_orders()
        self.assertEqual(res1, res2)
        mock_get.assert_called_once() # Still once

    @patch('src.services.brokerage_service.requests.get')
    def test_cache_expiration(self, mock_get):
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        # Force very short TTL for testing if possible, 
        # but here we'll just mock time.time() or wait.
        # Let's mock time.time() to simulate passage of time.
        
        with patch('src.services.brokerage_service.time.time') as mock_time:
            start_time = 1000.0
            mock_time.return_value = start_time
            
            # First call
            self.service.get_portfolio()
            self.assertEqual(mock_get.call_count, 1)
            
            # Call after 2 seconds - should use cache
            mock_time.return_value = start_time + 2.0
            self.service.get_portfolio()
            self.assertEqual(mock_get.call_count, 1)
            
            # Call after 6 seconds - should expire
            mock_time.return_value = start_time + 6.0
            self.service.get_portfolio()
            self.assertEqual(mock_get.call_count, 2)

if __name__ == '__main__':
    unittest.main()
