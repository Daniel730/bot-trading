import unittest
import pytz
from datetime import datetime
from unittest.mock import patch, MagicMock
from src.config import settings

class TestTimezoneSync(unittest.TestCase):
    def test_timezone_config(self):
        self.assertEqual(settings.MARKET_TIMEZONE, "America/New_York")
        self.assertEqual(settings.START_HOUR, 9)
        self.assertEqual(settings.START_MINUTE, 30)

    def test_market_hours_logic_nyc(self):
        market_tz = pytz.timezone("America/New_York")
        
        # 1. 10:00 AM NYC (Open)
        now_nyc = market_tz.localize(datetime(2026, 4, 6, 10, 0, 0)) # Monday
        opening = now_nyc.replace(hour=9, minute=30, second=0, microsecond=0)
        closing = now_nyc.replace(hour=16, minute=0, second=0, microsecond=0)
        
        is_open = opening <= now_nyc < closing
        self.assertTrue(is_open)

        # 2. 8:00 AM NYC (Closed)
        now_nyc = market_tz.localize(datetime(2026, 4, 6, 8, 0, 0))
        is_open = opening.replace(hour=9) <= now_nyc < closing.replace(hour=16)
        self.assertFalse(is_open)

        # 3. 5:00 PM NYC (Closed)
        now_nyc = market_tz.localize(datetime(2026, 4, 6, 17, 0, 0))
        is_open = opening.replace(hour=9) <= now_nyc < closing.replace(hour=16)
        self.assertFalse(is_open)

if __name__ == '__main__':
    unittest.main()
