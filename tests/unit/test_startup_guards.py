import pytest
import asyncio
from unittest.mock import MagicMock, patch
from src.monitor import ArbitrageMonitor
from src.config import settings

@pytest.mark.asyncio
async def test_startup_refusal_missing_baselines():
    """
    T006: Verify that ArbitrageMonitor refuses to boot if LIVE_CAPITAL_DANGER is True
    and Redis baselines are missing.
    """
    # Force LIVE_CAPITAL_DANGER = True
    with patch.object(settings, 'LIVE_CAPITAL_DANGER', True):
        # Mock Redis to return None (missing baseline)
        mock_redis = MagicMock()
        
        async def mock_get(key):
            return None
            
        mock_redis.get = mock_get
        
        with patch('src.monitor.redis_service') as mock_redis_service:
            mock_redis_service.client = mock_redis

            with patch('src.monitor.notification_service') as mock_notify:
                async def mock_send_message(msg): pass
                mock_notify.send_message = mock_send_message

                monitor = ArbitrageMonitor()

                # Should raise SystemExit
                with pytest.raises(SystemExit) as excinfo:
                    await monitor.verify_entropy_baselines([{'ticker_a': 'KO', 'ticker_b': 'PEP'}])

                assert "CRITICAL: Missing L2 Entropy Baselines" in str(excinfo.value)
@pytest.mark.asyncio
async def test_startup_success_with_baselines():
    """
    T006: Verify that ArbitrageMonitor proceeds if baselines exist.
    """
    with patch.object(settings, 'LIVE_CAPITAL_DANGER', True):
        # Mock Redis to return valid data
        mock_redis = MagicMock()
        
        async def mock_get(key):
            return "valid_baseline_data"
            
        mock_redis.get = mock_get
        
        with patch('src.monitor.redis_service') as mock_redis_service:
            mock_redis_service.client = mock_redis
            
            monitor = ArbitrageMonitor()
            # Should not raise exception
            await monitor.verify_entropy_baselines([{'ticker_a': 'KO', 'ticker_b': 'PEP'}])
