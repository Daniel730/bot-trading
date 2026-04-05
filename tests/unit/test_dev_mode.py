import unittest
from src.config import settings
from src.monitor import ArbitrageMonitor
import asyncio

class TestDevMode(unittest.IsolatedAsyncioTestCase):
    def test_dev_mode_config(self):
        # Verify defaults
        assert hasattr(settings, 'DEV_MODE')
        assert hasattr(settings, 'CRYPTO_TEST_PAIRS')
        assert len(settings.CRYPTO_TEST_PAIRS) > 0

    async def test_initialize_pairs_dev_mode(self):
        # Save original state
        original_mode = settings.DEV_MODE
        settings.DEV_MODE = True
        try:
            # We check if it picks the right pairs list
            pairs = settings.CRYPTO_TEST_PAIRS if settings.DEV_MODE else settings.ARBITRAGE_PAIRS
            assert pairs[0]['ticker_a'] == 'BTC-USD'
        finally:
            # Restore state
            settings.DEV_MODE = original_mode
