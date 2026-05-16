import os

import pytest

os.environ.setdefault("POSTGRES_PASSWORD", "strong-postgres-secret")
os.environ.setdefault("DASHBOARD_TOKEN", "strong-dashboard-token")

from src.config import Settings


@pytest.mark.parametrize("provider", ["T212", "WEB3"])
def test_unsupported_broker_provider_fails_closed(monkeypatch, provider):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.setenv("BROKERAGE_PROVIDER", provider)

    with pytest.raises(ValueError, match="BROKERAGE_PROVIDER.*ALPACA"):
        Settings(_env_file=None)
