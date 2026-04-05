import pytest
from datetime import datetime, timedelta
from src.services.dca_service import DCAService
from unittest.mock import MagicMock, patch

def test_next_run_calculation():
    service = DCAService()
    start = datetime(2026, 4, 5, 10, 0, 0)
    
    # Daily
    next_run = service.calculate_next_run('daily', start)
    assert next_run == start + timedelta(days=1)
    
    # Weekly
    next_run = service.calculate_next_run('weekly', start)
    assert next_run == start + timedelta(weeks=1)

def test_market_open_logic():
    service = DCAService()
    
    # Force DEV_MODE off for this test if needed, or mock settings
    with patch('src.services.dca_service.settings') as mock_settings:
        mock_settings.DEV_MODE = False
        
        # Tuesday 15:00 WET (Open)
        with patch('src.services.dca_service.datetime') as mock_date:
            mock_date.now.return_value = datetime(2026, 4, 7, 15, 0, 0)
            mock_date.fromisoformat = datetime.fromisoformat
            assert service.is_market_open() == True
            
            # Sunday (Closed)
            mock_date.now.return_value = datetime(2026, 4, 5, 15, 0, 0)
            assert service.is_market_open() == False
            
            # Tuesday 22:00 WET (Closed)
            mock_date.now.return_value = datetime(2026, 4, 7, 22, 0, 0)
            assert service.is_market_open() == False
