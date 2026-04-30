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


def test_default_dashboard_cors_regex_allows_tailscale_origins(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.delenv("DASHBOARD_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("DASHBOARD_ALLOWED_ORIGIN_REGEX", raising=False)

    settings = Settings(_env_file=None)

    assert re.fullmatch(settings.dashboard_allowed_origin_regex, "http://100.78.70.91:3000")
