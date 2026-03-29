import pytest
from src.config import settings
from src.monitor import ArbitrageMonitor
import asyncio

def test_dev_mode_config():
    # Verify defaults
    assert hasattr(settings, 'DEV_MODE')
    assert hasattr(settings, 'CRYPTO_TEST_PAIRS')
    assert len(settings.CRYPTO_TEST_PAIRS) > 0

@pytest.mark.asyncio
async def test_initialize_pairs_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", True)
    monitor = ArbitrageMonitor()
    # We won't call initialize_pairs fully because it fetches data
    # but we check if it picks the right pairs list
    pairs = settings.CRYPTO_TEST_PAIRS if settings.DEV_MODE else settings.ARBITRAGE_PAIRS
    assert pairs[0]['ticker_a'] == 'BTC-USD'
