import pytest
import time
from unittest.mock import patch, MagicMock
from src.services.data_service import DataService

def test_exponential_backoff_logic():
    """
    T013: Verifies that DataService.get_latest_price retries with backoff.
    """
    service = DataService()
    
    # We will mock yf.download to fail twice and then succeed
    import pandas as pd
    mock_df = pd.DataFrame({'Close': [150.0]}, index=[pd.Timestamp.now()])
    
    # side_effect with exceptions then success
    side_effects = [
        Exception("Attempt 1 Fail"),
        Exception("Attempt 2 Fail"),
        mock_df
    ]
    
    start_time = time.time()
    
    with patch('src.services.redis_service.redis_service.get_price', return_value=None):
        with patch('src.services.redis_service.redis_service.set_price'):
            with patch('src.services.data_service.settings') as mock_settings:
                mock_settings.DEV_MODE = False
                with patch('yfinance.download', side_effect=side_effects) as mock_yf:
                    # This should take approx 1s (1st wait) + 2s (2nd wait) = 3s
                    prices = service.get_latest_price(["AAPL"])
            
            duration = time.time() - start_time
            
            assert "AAPL" in prices
            assert prices["AAPL"] == 150.0
            assert mock_yf.call_count == 3
            # Allow some margin for execution time
            assert duration >= 3.0, f"Expected backoff duration >= 3s, got {duration:.2f}s"

if __name__ == "__main__":
    test_exponential_backoff_logic()
