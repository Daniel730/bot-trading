"""Scan-loop pacing helpers: bounded gather, ticker merge, result normalize."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from src.config import Settings
from src.monitor_scan_helpers import (
    gather_bounded,
    normalize_scan_results,
    open_signal_tickers,
)


@pytest.mark.asyncio
async def test_gather_bounded_caps_concurrency():
    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    async def work(n: int) -> int:
        nonlocal in_flight, peak
        async with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        return n

    results = await gather_bounded(
        (work(i) for i in range(8)),
        limit=2,
        return_exceptions=True,
    )

    assert results == list(range(8))
    assert peak <= 2


@pytest.mark.asyncio
async def test_gather_bounded_preserves_order_and_exceptions():
    async def ok(n: int) -> int:
        await asyncio.sleep(0.01 * (3 - n))
        return n

    async def boom() -> int:
        raise RuntimeError("storm")

    results = await gather_bounded(
        [ok(0), boom(), ok(2)],
        limit=3,
        return_exceptions=True,
    )

    assert results[0] == 0
    assert isinstance(results[1], RuntimeError)
    assert results[2] == 2


@pytest.mark.asyncio
async def test_gather_bounded_empty():
    assert await gather_bounded([], limit=2) == []


def test_open_signal_tickers_dedupes_preserving_order():
    signals = [
        {"legs": [{"ticker": "BTC-USD"}, {"ticker": "ETH-USD"}]},
        {"legs": [{"ticker": "ETH-USD"}, {"ticker": "SOL-USD"}]},
        {"legs": []},
        {"legs": [{"ticker": None}, {"ticker": "BTC-USD"}]},
    ]
    assert open_signal_tickers(signals) == ["BTC-USD", "ETH-USD", "SOL-USD"]


def test_normalize_scan_results_drops_exceptions():
    assert normalize_scan_results(
        [
            {"verdict": "OK"},
            RuntimeError("x"),
            {"verdict": "VETOED"},
            "ignore-me",
        ]
    ) == [{"verdict": "OK"}, {"verdict": "VETOED"}]


def test_scan_pacing_defaults(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    for key in (
        "SCAN_INTERVAL_SECONDS",
        "SCAN_PAIR_CONCURRENCY",
        "SCAN_EXIT_CONCURRENCY",
        "SCAN_COINT_RECHECK_CONCURRENCY",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)
    assert settings.SCAN_INTERVAL_SECONDS == 15
    assert settings.SCAN_PAIR_CONCURRENCY == 2
    assert settings.SCAN_EXIT_CONCURRENCY == 2
    assert settings.SCAN_COINT_RECHECK_CONCURRENCY == 1


@pytest.mark.parametrize(
    "env_key,bad_value",
    [
        ("SCAN_INTERVAL_SECONDS", "4"),
        ("SCAN_INTERVAL_SECONDS", "301"),
        ("SCAN_PAIR_CONCURRENCY", "0"),
        ("SCAN_PAIR_CONCURRENCY", "9"),
        ("SCAN_EXIT_CONCURRENCY", "0"),
        ("SCAN_COINT_RECHECK_CONCURRENCY", "5"),
    ],
)
def test_scan_pacing_bounds_reject_out_of_range(monkeypatch, env_key, bad_value):
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong-postgres-secret")
    monkeypatch.setenv("DASHBOARD_TOKEN", "strong-dashboard-token")
    monkeypatch.setenv(env_key, bad_value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.asyncio
async def test_evaluate_exit_uses_shared_prices_without_refetch(monitor):
    from unittest.mock import AsyncMock, MagicMock, patch

    signal = {
        "signal_id": "sig-1",
        "legs": [
            {"ticker": "AAPL", "quantity": 1, "side": "BUY", "price": 100.0},
            {"ticker": "MSFT", "quantity": 1, "side": "SELL", "price": 100.0},
        ],
        "total_cost_basis": 200.0,
    }
    shared = {"AAPL": 101.0, "MSFT": 99.0}

    with (
        patch("src.monitor.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_prices,
        patch("src.monitor.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_filter,
        patch("src.monitor.risk_service.check_financial_kill_switch", return_value=False),
        patch.object(monitor, "_close_position", new_callable=AsyncMock),
    ):
        kf = MagicMock()
        kf.calculate_spread_and_zscore.return_value = (0.0, 1.0)
        mock_filter.return_value = kf

        await monitor._evaluate_exit_conditions(signal, latest_prices=shared)

        mock_prices.assert_not_awaited()
