import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from src.services.brokerage_service import BrokerageService

class TestSlippageGuard(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        with patch('src.services.brokerage_service.settings') as mock_settings:
            mock_settings.T212_API_KEY = "test"
            mock_settings.T212_API_SECRET = "test"
            mock_settings.TRADING_212_MODE = "demo"
            self.service = BrokerageService()

    @patch('src.services.brokerage_service.requests.post')
    @patch('src.services.data_service.data_service.get_latest_price', new_callable=AsyncMock)
    @patch('src.services.brokerage_service.BrokerageService.get_symbol_metadata')
    async def test_place_value_order_buy_slippage(self, mock_metadata, mock_price, mock_post):
        mock_price.return_value = {"AAPL": 100.0}
        mock_metadata.return_value = {"minTradeQuantity": 0.0, "quantityIncrement": 0.0}
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"id": "1"})

        # Buy $100 of AAPL at $100/share -> 1 share
        await self.service.place_value_order("AAPL", 100.0, "BUY")

        args, kwargs = mock_post.call_args
        payload = kwargs['json']
        # limitPrice should be 100 * 1.01 = 101.0
        self.assertEqual(payload['limitPrice'], 101.0)
        self.assertIn("/orders/limit", args[0])

    @patch('src.services.brokerage_service.requests.post')
    @patch('src.services.data_service.data_service.get_latest_price', new_callable=AsyncMock)
    @patch('src.services.brokerage_service.BrokerageService.get_symbol_metadata')
    async def test_place_value_order_sell_slippage(self, mock_metadata, mock_price, mock_post):
        mock_price.return_value = {"AAPL": 100.0}
        mock_metadata.return_value = {"minTradeQuantity": 0.0, "quantityIncrement": 0.0}
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"id": "1"})

        # Sell $100 of AAPL at $100/share -> 1 share
        await self.service.place_value_order("AAPL", 100.0, "SELL")

        args, kwargs = mock_post.call_args
        payload = kwargs['json']
        # limitPrice should be 100 * 0.99 = 99.0
        self.assertEqual(payload['limitPrice'], 99.0)
        self.assertIn("/orders/limit", args[0])

if __name__ == '__main__':
    unittest.main()
