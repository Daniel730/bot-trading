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
