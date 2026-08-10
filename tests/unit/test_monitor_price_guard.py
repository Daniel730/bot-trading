import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import settings
from src.monitor import (
    CRYPTO_PRICE_MAX_AGE_SECONDS,
    CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT,
    CRYPTO_SNAPSHOT_STALE_TARGET_SECONDS,
    crypto_leg_freshness_marker,
    crypto_price_max_age_seconds,
    crypto_stale_repeat_limit,
    parse_price_timestamp,
)
from src.services.data_service import data_service


def test_crypto_snapshot_stale_repeat_limit_matches_runtime_cadence():
    assert CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT == 5
    assert CRYPTO_SNAPSHOT_STALE_TARGET_SECONDS == 120
    assert CRYPTO_PRICE_MAX_AGE_SECONDS == 180
    # Default SCAN_INTERVAL=15s => ceil(120/15)=8 repeats (~2 min wall clock).
    assert crypto_stale_repeat_limit(15) == 8
    assert crypto_stale_repeat_limit(settings.SCAN_INTERVAL_SECONDS) >= CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT
    # Slow scans keep the floor so we still trip within a few iterations.
    assert crypto_stale_repeat_limit(60) == CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT
    assert crypto_price_max_age_seconds(15) == float(CRYPTO_PRICE_MAX_AGE_SECONDS)
    assert crypto_price_max_age_seconds(30) == 240.0


def test_crypto_leg_freshness_marker_prefers_timestamp_over_price():
    assert crypto_leg_freshness_marker(
        "BTC-USD",
        76800.0,
        {"BTC-USD": "2026-08-04T08:00:00+00:00"},
    ) == ("ts", "2026-08-04T08:00:00+00:00")
    assert crypto_leg_freshness_marker("BTC-USD", 76800.0, {}) == ("price", 76800.0)
    assert crypto_leg_freshness_marker("BTC-USD", 76800.0, {"BTC-USD": ""}) == (
        "price",
        76800.0,
    )


def test_parse_price_timestamp_normalizes_naive_and_aware():
    aware = parse_price_timestamp("2026-08-04T08:00:00+00:00")
    assert aware == datetime(2026, 8, 4, 8, 0, tzinfo=timezone.utc)
    naive = parse_price_timestamp(datetime(2026, 8, 4, 8, 0))
    assert naive == datetime(2026, 8, 4, 8, 0, tzinfo=timezone.utc)
    assert parse_price_timestamp(None) is None
    assert parse_price_timestamp("not-a-timestamp") is None


@pytest.mark.asyncio
async def test_process_pair_missing_price_reports_skip_reason(monitor, caplog):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0}

    with patch.object(monitor, "is_market_open", return_value=True), \
         patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         caplog.at_level(logging.INFO, logger="src.monitor"):
        diagnostic = await monitor.process_pair(pair, latest_prices)

    assert diagnostic["verdict"] == "IGNORED"
    assert diagnostic["reason"] == "missing_price"
    assert "PAIR SKIP [AAPL/MSFT]: missing_price" in caplog.text
    mock_kf_get.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_pair_blocks_impossible_crypto_price_before_kalman(monitor, caplog):
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 9.45, "ETH-USD": 2110.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         caplog.at_level(logging.WARNING, logger="src.monitor"):
        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 1.0], 1.0, 0.0, 0.0)
        mock_kf_get.return_value = mock_kf

        diagnostic = await monitor.process_pair(pair, latest_prices)

    assert diagnostic["verdict"] == "IGNORED"
    assert diagnostic["reason"] == "price_sanity_invalid"
    mock_kf_get.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()
    assert "PRICE SANITY [BTC-USD/ETH-USD]" in caplog.text


@pytest.mark.asyncio
async def test_process_pair_blocks_alpaca_crypto_missing_timestamps_immediately(
    monitor, monkeypatch, caplog
):
    """Missing timestamps are invalid freshness — hard-block before Kalman (no trade)."""
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}
    monkeypatch.setattr(
        data_service,
        "last_price_sources",
        {"BTC-USD": "alpaca_crypto_snapshot", "ETH-USD": "alpaca_crypto_snapshot"},
    )
    monkeypatch.setattr(data_service, "last_price_timestamps", {}, raising=False)
    monkeypatch.setattr(settings, "SCAN_INTERVAL_SECONDS", 15)

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         caplog.at_level(logging.WARNING, logger="src.monitor"):

        mock_kf = MagicMock()
        mock_kf_get.return_value = mock_kf
        diagnostic = await monitor.process_pair(pair, dict(latest_prices))

    assert diagnostic["verdict"] == "IGNORED"
    assert diagnostic["reason"] == "price_freshness_unknown"
    mock_kf_get.assert_not_awaited()
    mock_save_state.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()
    assert "missing Alpaca timestamps" in caplog.text


@pytest.mark.asyncio
async def test_process_pair_blocks_mixed_crypto_sources_before_kalman(
    monitor, monkeypatch, caplog
):
    """Redis/yfinance mixed with Alpaca must not open trades (no trustworthy age)."""
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}
    fresh_ts = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    monkeypatch.setattr(
        data_service,
        "last_price_sources",
        {"BTC-USD": "alpaca_crypto_snapshot", "ETH-USD": "redis"},
    )
    monkeypatch.setattr(
        data_service,
        "last_price_timestamps",
        {"BTC-USD": fresh_ts},
        raising=False,
    )

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         caplog.at_level(logging.WARNING, logger="src.monitor"):
        mock_kf_get.return_value = MagicMock()
        diagnostic = await monitor.process_pair(pair, dict(latest_prices))

    assert diagnostic["reason"] == "price_freshness_unknown"
    mock_kf_get.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()
    assert "not both Alpaca" in caplog.text


@pytest.mark.asyncio
async def test_process_pair_blocks_single_leg_over_max_age(monitor, monkeypatch, caplog):
    """One stale Alpaca leg contaminating the pair must block the whole pair."""
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}
    monkeypatch.setattr(settings, "SCAN_INTERVAL_SECONDS", 15)
    max_age = crypto_price_max_age_seconds(15)
    fresh_ts = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    stale_ts = (
        datetime.now(timezone.utc) - timedelta(seconds=max_age + 30)
    ).isoformat()
    monkeypatch.setattr(
        data_service,
        "last_price_sources",
        {"BTC-USD": "alpaca_crypto_quote_mid", "ETH-USD": "alpaca_crypto_quote_mid"},
    )
    monkeypatch.setattr(
        data_service,
        "last_price_timestamps",
        {"BTC-USD": stale_ts, "ETH-USD": fresh_ts},
        raising=False,
    )

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         caplog.at_level(logging.WARNING, logger="src.monitor"):
        mock_kf_get.return_value = MagicMock()
        diagnostic = await monitor.process_pair(pair, dict(latest_prices))

    assert diagnostic["reason"] == "stale_price_snapshot"
    mock_kf_get.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()
    assert "BTC-USD" in caplog.text


@pytest.mark.asyncio
async def test_process_pair_allows_fresh_repeated_quote_mid_timestamp(monitor, monkeypatch, caplog):
    """Shared scan snapshot may reuse the same quote mid across scans; fresh age must pass."""
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}
    fresh_ts = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    monkeypatch.setattr(
        data_service,
        "last_price_sources",
        {"BTC-USD": "alpaca_crypto_quote_mid", "ETH-USD": "alpaca_crypto_quote_mid"},
    )
    monkeypatch.setattr(
        data_service,
        "last_price_timestamps",
        {"BTC-USD": fresh_ts, "ETH-USD": fresh_ts},
        raising=False,
    )
    monkeypatch.setattr(settings, "SCAN_INTERVAL_SECONDS", 15)

    # More iterations than the old hard-coded limit of 5 — must not false-reject.
    iterations = CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT + 3

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         caplog.at_level(logging.WARNING, logger="src.monitor"):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 1.0], 1.0, 0.0, 0.0)
        mock_kf_get.return_value = mock_kf

        diagnostics = [
            await monitor.process_pair(pair, dict(latest_prices))
            for _ in range(iterations)
        ]

    assert all(d["reason"] == "below_entry_threshold" for d in diagnostics)
    assert mock_kf_get.await_count == iterations
    assert mock_save_state.await_count == iterations
    mock_orchestrator.assert_not_awaited()
    assert "PRICE STALENESS" not in caplog.text
    assert pair["id"] not in monitor._crypto_snapshot_pair_prices


@pytest.mark.asyncio
async def test_process_pair_blocks_aged_alpaca_crypto_quote_mid_before_kalman(monitor, monkeypatch, caplog):
    """Truly stale quote timestamps (wall-clock age) still block before Kalman."""
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}
    monkeypatch.setattr(settings, "SCAN_INTERVAL_SECONDS", 15)
    max_age = crypto_price_max_age_seconds(15)
    stale_ts = (
        datetime.now(timezone.utc) - timedelta(seconds=max_age + 30)
    ).isoformat()
    monkeypatch.setattr(
        data_service,
        "last_price_sources",
        {"BTC-USD": "alpaca_crypto_quote_mid", "ETH-USD": "alpaca_crypto_quote_mid"},
    )
    monkeypatch.setattr(
        data_service,
        "last_price_timestamps",
        {"BTC-USD": stale_ts, "ETH-USD": stale_ts},
        raising=False,
    )

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         caplog.at_level(logging.WARNING, logger="src.monitor"):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 1.0], 1.0, 0.0, 0.0)
        mock_kf_get.return_value = mock_kf

        diagnostic = await monitor.process_pair(pair, dict(latest_prices))

    assert diagnostic["verdict"] == "IGNORED"
    assert diagnostic["reason"] == "stale_price_snapshot"
    mock_kf_get.assert_not_awaited()
    mock_save_state.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()
    assert "timestamp age" in caplog.text


@pytest.mark.asyncio
async def test_process_pair_snapshot_with_advancing_timestamps_not_false_stale(
    monitor, monkeypatch, caplog
):
    """Flat snapshot prices with advancing trade timestamps must not trip price-identity stale."""
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}
    monkeypatch.setattr(
        data_service,
        "last_price_sources",
        {"BTC-USD": "alpaca_crypto_snapshot", "ETH-USD": "alpaca_crypto_snapshot"},
    )
    monkeypatch.setattr(settings, "SCAN_INTERVAL_SECONDS", 15)

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         caplog.at_level(logging.WARNING, logger="src.monitor"):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 1.0], 1.0, 0.0, 0.0)
        mock_kf_get.return_value = mock_kf

        iterations = crypto_stale_repeat_limit(15) + 1
        diagnostics = []
        base = datetime.now(timezone.utc) - timedelta(seconds=10)
        for i in range(iterations):
            monkeypatch.setattr(
                data_service,
                "last_price_timestamps",
                {
                    "BTC-USD": (base + timedelta(seconds=i)).isoformat(),
                    "ETH-USD": (base + timedelta(seconds=i + 1)).isoformat(),
                },
                raising=False,
            )
            diagnostics.append(await monitor.process_pair(pair, dict(latest_prices)))

    assert all(d["reason"] == "below_entry_threshold" for d in diagnostics)
    assert mock_kf_get.await_count == iterations
    assert mock_save_state.await_count == iterations
    mock_orchestrator.assert_not_awaited()
    assert "PRICE STALENESS" not in caplog.text


@pytest.mark.asyncio
async def test_process_pair_quote_mid_missing_timestamp_hard_blocks(
    monitor, monkeypatch, caplog
):
    """Missing quote-mid timestamps hard-reject (invalid freshness ≠ tradeable)."""
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}
    monkeypatch.setattr(
        data_service,
        "last_price_sources",
        {"BTC-USD": "alpaca_crypto_quote_mid", "ETH-USD": "alpaca_crypto_quote_mid"},
    )
    monkeypatch.setattr(data_service, "last_price_timestamps", {}, raising=False)
    monkeypatch.setattr(settings, "SCAN_INTERVAL_SECONDS", 60)

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock), \
         caplog.at_level(logging.WARNING, logger="src.monitor"):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 1.0], 1.0, 0.0, 0.0)
        mock_kf_get.return_value = mock_kf

        first = await monitor.process_pair(pair, dict(latest_prices))

    assert first["reason"] == "price_freshness_unknown"
    mock_kf_get.assert_not_awaited()
    assert "missing Alpaca timestamps" in caplog.text
