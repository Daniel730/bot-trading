import os
import re

import pytest

os.environ.setdefault("POSTGRES_PASSWORD", "strong-postgres-secret")
os.environ.setdefault("DASHBOARD_TOKEN", "strong-dashboard-token")

from src.config import Settings


def test_settings_accepts_docker_quoted_crypto_token_mapping(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.setenv("CRYPTO_TOKEN_MAPPING", '\'{"USDC":{"address":"","decimals":6}}\'')

    settings = Settings(_env_file=None)

    assert settings.CRYPTO_TOKEN_MAPPING["USDC"]["decimals"] == 6


def test_dashboard_cors_wildcard_requires_dev_mode(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.setenv("DASHBOARD_ALLOWED_ORIGINS", "*")
    monkeypatch.setenv("DEV_MODE", "false")

    with pytest.raises(ValueError, match="DASHBOARD_ALLOWED_ORIGINS"):
        Settings(_env_file=None)


def test_live_mode_requires_explicit_live_capital_danger(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.setenv("PAPER_TRADING", "false")
    monkeypatch.setenv("LIVE_CAPITAL_DANGER", "false")

    with pytest.raises(ValueError, match="PAPER_TRADING=false requires LIVE_CAPITAL_DANGER=true"):
        Settings(_env_file=None)


def test_default_dashboard_cors_regex_allows_tailscale_origins(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.delenv("DASHBOARD_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("DASHBOARD_ALLOWED_ORIGIN_REGEX", raising=False)

    settings = Settings(_env_file=None)

    assert re.fullmatch(settings.dashboard_allowed_origin_regex, "http://localhost:3000")


def test_guard_monitor_entry_zscore_clamps_dangerous_override():
    from src.config import _guard_monitor_entry_zscore

    assert _guard_monitor_entry_zscore(0.5) == 1.0
    assert _guard_monitor_entry_zscore(2.0) == 2.0
