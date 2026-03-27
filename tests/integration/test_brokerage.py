import unittest
from unittest.mock import patch, MagicMock
from src.services.brokerage_service import BrokerageService

class TestBrokerageServiceIntegration(unittest.TestCase):
    def setUp(self):
        self.service = BrokerageService(demo=True)
        self.service.auth = ("dummy_key", "dummy_secret")

    @patch('src.services.brokerage_service.requests.post')
    def test_execute_market_order_success(self, mock_post):
        # Mocking successful 201 response for T212 Market Order
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "order-123", "status": "FILLED"}
        mock_post.return_value = mock_response

        result = self.service.execute_market_order("AAPL", 1.5)
        
        self.assertEqual(result["id"], "order-123")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['ticker'], "AAPL")
        self.assertEqual(kwargs['json']['quantity'], 1.5)

    @patch('src.services.brokerage_service.requests.get')
    def test_get_positions_success(self, mock_get):
        # Mocking successful 200 response for T212 Portfolio
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"ticker": "AAPL", "quantity": 10.0}]
        mock_get.return_value = mock_response

        result = self.service.get_positions()
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ticker"], "AAPL")
        mock_get.assert_called_once()

    @patch('src.services.brokerage_service.requests.get')
    def test_get_cash_balance_success(self, mock_get):
        # Mocking successful 200 response for T212 Cash Balance
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"free": 5000.0, "total": 10000.0}
        mock_get.return_value = mock_response

        balance = self.service.get_cash_balance()
        
        self.assertEqual(balance, 5000.0)
        mock_get.assert_called_once()

if __name__ == '__main__':
    unittest.main()
