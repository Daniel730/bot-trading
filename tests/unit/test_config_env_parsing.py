import pytest

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
