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


def test_take_profit_force_exit_clamped_to_take_profit_band(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.setenv("TAKE_PROFIT_ZSCORE", "0.5")
    monkeypatch.setenv("TAKE_PROFIT_FORCE_EXIT_ZSCORE", "1.5")

    settings = Settings(_env_file=None)

    assert settings.TAKE_PROFIT_FORCE_EXIT_ZSCORE == pytest.approx(0.5)


def test_default_dashboard_cors_regex_allows_tailscale_origins(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.delenv("DASHBOARD_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("DASHBOARD_ALLOWED_ORIGIN_REGEX", raising=False)

    settings = Settings(_env_file=None)

    assert re.fullmatch(settings.dashboard_allowed_origin_regex, "http://localhost:3000")


def test_guard_monitor_entry_zscore_clamps_dangerous_override():
    from src.config import MONITOR_ENTRY_ZSCORE_MIN, _guard_monitor_entry_zscore

    assert MONITOR_ENTRY_ZSCORE_MIN == 1.0
    assert _guard_monitor_entry_zscore(0.5) == 1.0
    assert _guard_monitor_entry_zscore(0.99) == 1.0
    assert _guard_monitor_entry_zscore(1.0) == 1.0
    assert _guard_monitor_entry_zscore(2.0) == 2.0


def test_env_monitor_entry_zscore_below_floor_is_clamped(monkeypatch):
    """Env MONITOR_ENTRY_ZSCORE=0.5 must not silently stick on Settings."""
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.setenv("MONITOR_ENTRY_ZSCORE", "0.5")

    settings = Settings(_env_file=None)

    assert settings.MONITOR_ENTRY_ZSCORE == 1.0


def test_validate_runtime_settings_update_writes_clamped_entry_z_back(monkeypatch):
    """Dashboard setattr must receive the clamped value, not the raw 0.5."""
    from src.config import settings, validate_runtime_settings_update

    monkeypatch.setattr(settings, "MONITOR_ENTRY_ZSCORE", 2.0)
    updates = {"MONITOR_ENTRY_ZSCORE": 0.5}

    validate_runtime_settings_update(updates)

    assert updates["MONITOR_ENTRY_ZSCORE"] == 1.0
    # Live settings restored after validation probe.
    assert settings.MONITOR_ENTRY_ZSCORE == 2.0


def test_save_settings_override_persists_clamped_entry_z(tmp_path, monkeypatch):
    import json

    from src import config as config_mod

    override_path = tmp_path / "bot_settings.json"
    monkeypatch.setattr(config_mod, "BOT_SETTINGS_OVERRIDE_PATH", override_path)

    config_mod.save_settings_override({"MONITOR_ENTRY_ZSCORE": 0.5, "SCAN_INTERVAL_SECONDS": 20})

    stored = json.loads(override_path.read_text(encoding="utf-8"))
    assert stored["MONITOR_ENTRY_ZSCORE"] == 1.0
    assert stored["SCAN_INTERVAL_SECONDS"] == 20


def test_default_pair_denylist_covers_both_btc_bch_orders(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.delenv("PAIR_DENYLIST", raising=False)
    monkeypatch.delenv("PAIR_DISCOVERY_AUTO_PROMOTE", raising=False)
    monkeypatch.delenv("PAIR_DISCOVERY_MAX_ABS_HEDGE", raising=False)
    monkeypatch.delenv("PAIR_DISCOVERY_MIN_ABS_HEDGE", raising=False)
    monkeypatch.delenv("PAIR_DISCOVERY_MIN_CORRELATION", raising=False)
    monkeypatch.delenv("PAIR_DISCOVERY_MAX_PVALUE", raising=False)

    settings = Settings(_env_file=None)
    denied = settings.pair_denylist_ids

    assert "BTC-USD_BCH-USD" in denied
    assert "BCH-USD_BTC-USD" in denied
    assert settings.PAIR_DISCOVERY_AUTO_PROMOTE is True
    assert settings.PAIR_DISCOVERY_MAX_ABS_HEDGE == 25.0
    assert settings.PAIR_DISCOVERY_MIN_ABS_HEDGE == 0.05
    assert settings.PAIR_DISCOVERY_MIN_CORRELATION == 0.70
    assert settings.PAIR_DISCOVERY_MAX_PVALUE == 0.05
    assert settings.CRYPTO_COINTEGRATION_PVALUE_THRESHOLD == 0.10
    assert settings.TAKE_PROFIT_FORCE_EXIT_ZSCORE == 0.25
    assert settings.MAX_OPEN_PAIRS == 8
    assert settings.MAX_PORTFOLIO_GROSS_NOTIONAL_USD == 800.0
    assert settings.BLOCK_SHARED_LEG_OPENS is True
    assert settings.MAX_SECTOR_EXPOSURE == 0.30


def test_pair_discovery_min_abs_hedge_env_override(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.setenv("PAIR_DISCOVERY_MIN_ABS_HEDGE", "0.10")

    settings = Settings(_env_file=None)
    assert settings.PAIR_DISCOVERY_MIN_ABS_HEDGE == 0.10


def test_pair_denylist_env_override_normalizes_both_orders(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.setenv("PAIR_DENYLIST", "btc-usd_bch-usd")

    settings = Settings(_env_file=None)
    denied = settings.pair_denylist_ids

    assert "BTC-USD_BCH-USD" in denied
    assert "BCH-USD_BTC-USD" in denied
