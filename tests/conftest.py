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
