from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import settings


def test_requires_l2_entropy_baselines_false_when_live_capital_danger_off(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", False)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://api.alpaca.markets")

    assert settings.requires_l2_entropy_baselines is False


def test_requires_l2_entropy_baselines_false_for_shadow_paper(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "PAPER_TRADING", True)
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://api.alpaca.markets")

    assert settings.requires_l2_entropy_baselines is False


def test_requires_l2_entropy_baselines_false_for_alpaca_paper_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    assert settings.requires_l2_entropy_baselines is False


def test_requires_l2_entropy_baselines_false_for_dev_mode_on_paper_api(monkeypatch):
    """DEV_MODE excludes broker_paper_trading, but paper-api must still skip the gate."""
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "DEV_MODE", True)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    assert settings.is_broker_paper_trading is False
    assert settings.is_alpaca_paper_endpoint is True
    assert settings.requires_l2_entropy_baselines is False


def test_requires_l2_entropy_baselines_true_for_live_api(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://api.alpaca.markets")

    assert settings.requires_l2_entropy_baselines is True


def test_requires_l2_entropy_baselines_true_for_dev_mode_on_live_api(monkeypatch):
    """DEV_MODE on a live URL remains gated — only paper-api is exempt."""
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "DEV_MODE", True)
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://api.alpaca.markets")

    assert settings.requires_l2_entropy_baselines is True


async def _init_pairs_with_entropy_spy(monkeypatch, startup_monitor_factory, pairs):
    monitor = startup_monitor_factory()
    monitor.verify_entropy_baselines = AsyncMock()
    monkeypatch.setattr(
        "src.monitor.persistence_service.get_active_trading_pairs",
        AsyncMock(return_value=pairs),
    )
    monkeypatch.setattr("src.monitor.build_candidate_pairs", MagicMock(return_value=pairs))
    monkeypatch.setattr("src.monitor.filter_pair_universe", AsyncMock(return_value=(pairs, [])))
    monkeypatch.setattr("src.monitor.dashboard_service.update", AsyncMock())
    monkeypatch.setattr(
        "src.monitor.data_service.get_historical_data_async",
        AsyncMock(return_value=None),
    )
    await monitor.initialize_pairs()
    return monitor


@pytest.mark.asyncio
async def test_alpaca_paper_broker_startup_skips_live_entropy_baselines(
    monkeypatch, startup_monitor_factory
):
    pairs = [{"ticker_a": "BTC-USD", "ticker_b": "ETH-USD"}]
    monitor = startup_monitor_factory()
    monitor.verify_entropy_baselines = AsyncMock(
        side_effect=AssertionError("Alpaca paper broker mode must not require live entropy baselines")
    )

    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setattr("src.monitor.persistence_service.get_active_trading_pairs", AsyncMock(return_value=pairs))
    monkeypatch.setattr("src.monitor.build_candidate_pairs", MagicMock(return_value=pairs))
    monkeypatch.setattr("src.monitor.filter_pair_universe", AsyncMock(return_value=(pairs, [])))
    monkeypatch.setattr("src.monitor.dashboard_service.update", AsyncMock())
    monkeypatch.setattr("src.monitor.data_service.get_historical_data_async", AsyncMock(return_value=None))

    await monitor.initialize_pairs()

    monitor.verify_entropy_baselines.assert_not_awaited()


@pytest.mark.asyncio
async def test_dev_mode_paper_api_startup_skips_live_entropy_baselines(
    monkeypatch, startup_monitor_factory
):
    """Regression: DEV_MODE makes broker_paper_trading False; paper-api must still skip."""
    pairs = [{"ticker_a": "BTC-USD", "ticker_b": "ETH-USD"}]
    monkeypatch.setattr(settings, "DEV_MODE", True)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    monitor = await _init_pairs_with_entropy_spy(monkeypatch, startup_monitor_factory, pairs)

    assert settings.is_broker_paper_trading is False
    monitor.verify_entropy_baselines.assert_not_awaited()


@pytest.mark.asyncio
async def test_shadow_paper_startup_skips_live_entropy_baselines(
    monkeypatch, startup_monitor_factory
):
    pairs = [{"ticker_a": "KO", "ticker_b": "PEP"}]
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "PAPER_TRADING", True)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://api.alpaca.markets")

    monitor = await _init_pairs_with_entropy_spy(monkeypatch, startup_monitor_factory, pairs)

    monitor.verify_entropy_baselines.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_api_startup_enforces_entropy_baselines(
    monkeypatch, startup_monitor_factory
):
    pairs = [{"ticker_a": "KO", "ticker_b": "PEP"}]
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", True)
    monkeypatch.setattr(settings, "BROKERAGE_PROVIDER", "ALPACA")
    monkeypatch.setattr(settings, "ALPACA_BASE_URL", "https://api.alpaca.markets")

    monitor = await _init_pairs_with_entropy_spy(monkeypatch, startup_monitor_factory, pairs)

    monitor.verify_entropy_baselines.assert_awaited_once_with(pairs)


@pytest.mark.asyncio
async def test_startup_refusal_missing_baselines(startup_monitor_factory):
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

                monitor = startup_monitor_factory()

                # Should raise SystemExit
                with pytest.raises(SystemExit) as excinfo:
                    await monitor.verify_entropy_baselines([{'ticker_a': 'KO', 'ticker_b': 'PEP'}])

                assert "CRITICAL: Missing L2 Entropy Baselines" in str(excinfo.value)


@pytest.mark.asyncio
async def test_startup_success_with_baselines(startup_monitor_factory):
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

            monitor = startup_monitor_factory()
            # Should not raise exception
            await monitor.verify_entropy_baselines([{'ticker_a': 'KO', 'ticker_b': 'PEP'}])
