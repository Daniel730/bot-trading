import unittest
from unittest.mock import patch, MagicMock
from src.services.brokerage_service import BrokerageService
from src.config import settings

class TestBrokerageServiceIntegration(unittest.TestCase):
    def setUp(self):
        # Patch settings instead of service module
        self.patcher_key = patch.object(settings, 'T212_API_KEY', 'test_key')
        self.patcher_mode = patch.object(settings, 'TRADING_212_MODE', 'demo')
        self.patcher_key.start()
        self.patcher_mode.start()
        self.service = BrokerageService()

    def tearDown(self):
        self.patcher_key.stop()
        self.patcher_mode.stop()

    @patch('src.services.brokerage_service.requests.post')
    def test_place_market_order_success(self, mock_post):
        # Mocking successful 200 response for T212 Market Order (v1 returns 200)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "order-123", "status": "FILLED"}
        mock_post.return_value = mock_response

        result = self.service.place_market_order("KO", 1.0, "BUY")
        
        self.assertEqual(result["id"], "order-123")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        
        # Verify Auth Header (Public API v1 uses direct key)
        auth_header = kwargs['headers']['Authorization']
        self.assertEqual(auth_header, "test_key")
        
        # Verify Payload
        self.assertEqual(kwargs['json']['symbol'], "KO_US_EQ")
        self.assertEqual(kwargs['json']['quantity'], 1.0)
        self.assertEqual(kwargs['json']['side'], "BUY")

    @patch('src.services.brokerage_service.requests.get')
    def test_get_portfolio_success(self, mock_get):
        # Mocking successful 200 response for T212 Portfolio
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"ticker": "KO", "quantity": 10.0}]
        mock_get.return_value = mock_response

        result = self.service.get_portfolio()
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ticker"], "KO")
        mock_get.assert_called_once()

if __name__ == '__main__':
    unittest.main()
