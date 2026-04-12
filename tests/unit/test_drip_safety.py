import unittest
from unittest.mock import patch, MagicMock
from src.services.brokerage_service import BrokerageService

class TestDRIPSafety(unittest.TestCase):
    def setUp(self):
        with patch('src.services.brokerage_service.settings') as mock_settings:
            mock_settings.T212_API_KEY = "test"
            mock_settings.T212_API_SECRET = "test"
            mock_settings.TRADING_212_MODE = "demo"
            self.service = BrokerageService()

    @patch('src.services.brokerage_service.requests.get')
    @patch('src.services.brokerage_service.BrokerageService.place_value_order')
    @patch('src.services.brokerage_service.BrokerageService.get_account_cash')
    def test_drip_safety_cap_dividend_is_limit(self, mock_cash, mock_place, mock_get):
        # Dividend $10, Available $100 -> execution value should be $10
        mock_cash.return_value = 100.0
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [{"type": "DIVIDEND", "ticker": "AAPL", "amount": 10.0}])
        mock_place.return_value = {"status": "success"}

        self.service.check_dividends_and_reinvest()
        
        mock_place.assert_called_with("AAPL", 10.0, "BUY")

    @patch('src.services.brokerage_service.requests.get')
    @patch('src.services.brokerage_service.BrokerageService.place_value_order')
    @patch('src.services.brokerage_service.BrokerageService.get_account_cash')
    def test_drip_safety_cap_cash_is_limit(self, mock_cash, mock_place, mock_get):
        # Dividend $10, Available $2 -> execution value should be $2
        mock_cash.return_value = 2.0
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [{"type": "DIVIDEND", "ticker": "AAPL", "amount": 10.0}])
        mock_place.return_value = {"status": "success"}

        self.service.check_dividends_and_reinvest()
        
        mock_place.assert_called_with("AAPL", 2.0, "BUY")

    @patch('src.services.brokerage_service.requests.get')
    @patch('src.services.brokerage_service.BrokerageService.place_value_order')
    @patch('src.services.brokerage_service.BrokerageService.get_account_cash')
    def test_drip_skips_small_amount(self, mock_cash, mock_place, mock_get):
        # Dividend $0.50, Available $100 -> execution value $0.50 < $1.00 -> Skip
        mock_cash.return_value = 100.0
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [{"type": "DIVIDEND", "ticker": "AAPL", "amount": 0.50}])

        self.service.check_dividends_and_reinvest()
        
        mock_place.assert_not_called()

if __name__ == '__main__':
    unittest.main()
