import unittest
import base64
from unittest.mock import patch, MagicMock
from src.services.brokerage_service import BrokerageService

class TestBrokerageServiceIntegration(unittest.TestCase):
    def setUp(self):
        with patch('src.services.brokerage_service.T212_API_KEY', 'test_key'), \
             patch('src.services.brokerage_service.T212_API_SECRET', 'test_secret'):
            self.service = BrokerageService(demo=True)

    @patch('src.services.brokerage_service.requests.post')
    def test_place_market_order_basic_auth(self, mock_post):
        # Mocking successful 201 response for T212 Market Order
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "order-123", "status": "FILLED"}
        mock_post.return_value = mock_response

        # Disable rate limit sleep for testing
        self.service.rate_limit_seconds = 0

        result = self.service.place_market_order("KO", -1.0)
        
        self.assertEqual(result["id"], "order-123")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        
        # Verify Basic Auth Header
        auth_header = kwargs['headers']['Authorization']
        self.assertTrue(auth_header.startswith("Basic "))
        
        # Verify Payload
        self.assertEqual(kwargs['json']['ticker'], "KO")
        self.assertEqual(kwargs['json']['quantity'], -1.0)

    @patch('src.services.brokerage_service.requests.get')
    def test_fetch_positions_success(self, mock_get):
        # Mocking successful 200 response for T212 Portfolio
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"ticker": "KO", "quantity": 10.0}]
        mock_get.return_value = mock_response

        result = self.service.fetch_positions()
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ticker"], "KO")
        mock_get.assert_called_once()
        
        # Verify Auth Header in GET
        auth_header = mock_get.call_args[1]['headers']['Authorization']
        self.assertTrue(auth_header.startswith("Basic "))

if __name__ == '__main__':
    unittest.main()
