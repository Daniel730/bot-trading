import pytest

from tests.fakes import FakeBroker, FakeMarketData, FakePersistence, FakeRedis


@pytest.fixture
def fake_broker():
    return FakeBroker()


@pytest.fixture
def fake_market_data():
    return FakeMarketData()


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def fake_persistence():
    return FakePersistence()


@pytest.fixture
def startup_monitor_factory(fake_broker):
    from unittest.mock import patch

    from src.monitor import ArbitrageMonitor

    def make_startup_monitor(mode: str = "live") -> ArbitrageMonitor:
        return ArbitrageMonitor(mode=mode)

    with patch("src.monitor.BrokerageService", return_value=fake_broker):
        yield make_startup_monitor


@pytest.fixture
def startup_health_check_connection():
    class StartupHealthCheckConnection:
        def __init__(self, error=None):
            self._error = error

        async def __aenter__(self):
            if self._error:
                raise self._error
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    return StartupHealthCheckConnection


@pytest.fixture
def monitor(monkeypatch):
    from unittest.mock import AsyncMock, patch

    from src.monitor import ArbitrageMonitor
    from src.services.persistence_service import persistence_service

    with patch("src.monitor.BrokerageService") as mock_broker_class:
        monkeypatch.setattr(persistence_service, "get_open_signals", AsyncMock(return_value=[]))
        monitor_instance = ArbitrageMonitor(mode="live")
        monitor_instance.brokerage = mock_broker_class.return_value
        monitor_instance.brokerage.get_venue.return_value = "ALPACA"
        monitor_instance.brokerage.get_available_quantity = AsyncMock(return_value=1_000_000.0)
        monitor_instance.brokerage.get_pending_orders = AsyncMock(return_value=[])
        monitor_instance.brokerage.get_pending_orders_value.return_value = 0.0
        monitor_instance.brokerage.get_account_cash.return_value = 10000.0
        monitor_instance.brokerage.get_account_equity.return_value = 10000.0
        monitor_instance.brokerage.get_account_buying_power.return_value = 10000.0
        monitor_instance.brokerage.get_positions = AsyncMock(
            return_value=[
                {
                    "quantity": 1_000_000.0,
                    "quantityAvailableForTrading": 1_000_000.0,
                    "marketValue": 1_000_000.0,
                }
            ]
        )
        monkeypatch.setattr(persistence_service, "update_trade_fill", AsyncMock(), raising=False)
        return monitor_instance
