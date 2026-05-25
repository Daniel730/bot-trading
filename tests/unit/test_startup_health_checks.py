from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import settings
from src.monitor import ArbitrageMonitor


class _HealthCheckConnection:
    def __init__(self, error=None):
        self._error = error

    async def __aenter__(self):
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_startup_monitor(mode: str = "live") -> ArbitrageMonitor:
    return ArbitrageMonitor(mode=mode)


@pytest.fixture
def startup_monitor_factory(fake_broker):
    with patch("src.monitor.BrokerageService", return_value=fake_broker):
        yield _make_startup_monitor


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failing_check", "expected_message"),
    [
        ("postgres", "PostgreSQL connection failed"),
        ("redis", "Redis connection failed"),
        ("alpaca", "Alpaca API connection failed"),
    ],
)
@patch("src.monitor.notification_service")
@patch("src.monitor.redis_service")
@patch("src.monitor.dashboard_service")
@patch("src.monitor.persistence_service")
async def test_startup_health_check_failures_use_existing_notification_api(
    mock_persistence,
    mock_dashboard,
    mock_redis,
    mock_notify,
    failing_check,
    expected_message,
    startup_monitor_factory,
):
    monitor = startup_monitor_factory()
    monitor.log_preflight = MagicMock()
    monitor.active_pairs = [{"ticker_a": "KO", "ticker_b": "PEP"}]
    monitor.initialize_pairs = AsyncMock()
    monitor.brokerage.get_portfolio = AsyncMock(return_value=[])
    mock_persistence.init_db = AsyncMock()
    mock_persistence.engine.connect.return_value = _HealthCheckConnection()
    mock_dashboard.attach_monitor = MagicMock()
    mock_dashboard.start = AsyncMock()
    mock_notify.start_listening = AsyncMock()
    mock_notify.send_message = AsyncMock()
    mock_redis.client.ping = AsyncMock()

    if failing_check == "postgres":
        mock_persistence.engine.connect.return_value = _HealthCheckConnection(RuntimeError("pg offline"))
    elif failing_check == "redis":
        mock_redis.client.ping.side_effect = RuntimeError("redis offline")
    else:
        monitor.brokerage.get_portfolio.side_effect = RuntimeError("alpaca offline")

    with patch.object(settings, "PAPER_TRADING", failing_check != "alpaca"), patch(
        "src.monitor.asyncio.sleep", AsyncMock()
    ):
        await monitor.run()

    mock_notify.send_message.assert_awaited()
    assert expected_message in mock_notify.send_message.await_args_list[-1].args[0]
