import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from src.services.brokerage_service import BrokerageService
from src.config import settings

class TestBrokerageServiceIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Patch settings instead of service module
        self.patcher_key = patch.object(settings, 'T212_API_KEY', 'test_key')
        self.patcher_mode = patch.object(settings, 'TRADING_212_MODE', 'demo')
        self.patcher_key.start()
        self.patcher_mode.start()
        self.service = BrokerageService()

    async def asyncTearDown(self):
        self.patcher_key.stop()
        self.patcher_mode.stop()

    @patch('src.services.brokerage_service.requests.post')
    def test_place_market_order_success(self, mock_post):
        # ...
        result = self.service.place_market_order("KO", 1.0, "BUY")
        # ... (rest of method remains same)

    async def test_get_portfolio_success(self):
        # Mocking successful 200 response for T212 Portfolio
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"ticker": "KO", "quantity": 10.0}]
        
        with patch.object(self.service.session, 'get', return_value=mock_response) as mock_get:
            # S-08 Fix: Added await
            result = await self.service.get_portfolio()
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["ticker"], "KO")
            mock_get.assert_called_once()

if __name__ == '__main__':
    unittest.main()
