import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from src.services.brokerage_service import BrokerageService

class TestDRIPSafety(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        with patch('src.services.brokerage_service.settings') as mock_settings:
            mock_settings.T212_API_KEY = "test"
            mock_settings.T212_API_SECRET = "test"
            mock_settings.TRADING_212_MODE = "demo"
            self.service = BrokerageService()

    @patch('src.services.brokerage_service.BrokerageService.get_account_cash')
    @patch('src.services.brokerage_service.BrokerageService.place_value_order', new_callable=AsyncMock)
    async def test_drip_safety_cap_dividend_is_limit(self, mock_place, mock_cash):
        with patch.object(self.service.session, 'get') as mock_get:
            mock_cash.return_value = 100.0
            mock_get.return_value = MagicMock(status_code=200, json=lambda: [{"type": "DIVIDEND", "ticker": "AAPL", "amount": 10.0}])
            mock_place.return_value = {"status": "success"}

            await self.service.check_dividends_and_reinvest()

        mock_place.assert_awaited_with("AAPL", 10.0, "BUY")

    @patch('src.services.brokerage_service.BrokerageService.get_account_cash')
    @patch('src.services.brokerage_service.BrokerageService.place_value_order', new_callable=AsyncMock)
    async def test_drip_safety_cap_cash_is_limit(self, mock_place, mock_cash):
        with patch.object(self.service.session, 'get') as mock_get:
            mock_cash.return_value = 2.0
            mock_get.return_value = MagicMock(status_code=200, json=lambda: [{"type": "DIVIDEND", "ticker": "AAPL", "amount": 10.0}])
            mock_place.return_value = {"status": "success"}

            await self.service.check_dividends_and_reinvest()

        mock_place.assert_awaited_with("AAPL", 2.0, "BUY")

    @patch('src.services.brokerage_service.BrokerageService.place_value_order')
    @patch('src.services.brokerage_service.BrokerageService.get_account_cash')
    async def test_drip_skips_small_amount(self, mock_cash, mock_place):
        with patch.object(self.service.session, 'get') as mock_get:
            mock_cash.return_value = 100.0
            mock_get.return_value = MagicMock(status_code=200, json=lambda: [{"type": "DIVIDEND", "ticker": "AAPL", "amount": 0.50}])

            await self.service.check_dividends_and_reinvest()

        mock_place.assert_not_called()

if __name__ == '__main__':
    unittest.main()
