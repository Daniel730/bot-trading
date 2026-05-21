import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.monitor import ArbitrageMonitor, CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT
from src.services.data_service import data_service
from src.services.persistence_service import persistence_service


def test_crypto_snapshot_stale_repeat_limit_matches_runtime_cadence():
    assert CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT == 5


@pytest.fixture
def monitor(monkeypatch):
    with patch("src.monitor.BrokerageService") as mock_broker_class:
        monkeypatch.setattr(persistence_service, "get_open_signals", AsyncMock(return_value=[]))
        m = ArbitrageMonitor(mode="live")
        m.brokerage = mock_broker_class.return_value
        m.brokerage.get_venue.return_value = "ALPACA"
        m.brokerage.get_available_quantity = AsyncMock(return_value=1_000_000.0)
        m.brokerage.get_pending_orders = AsyncMock(return_value=[])
        m.brokerage.get_pending_orders_value.return_value = 0.0
        m.brokerage.get_account_cash.return_value = 10000.0
        m.brokerage.get_account_equity.return_value = 10000.0
        m.brokerage.get_account_buying_power.return_value = 10000.0
        monkeypatch.setattr(persistence_service, "update_trade_fill", AsyncMock(), raising=False)
        return m


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
async def test_process_pair_blocks_repeated_alpaca_crypto_snapshot_before_kalman(monitor, monkeypatch, caplog):
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}
    monkeypatch.setattr(
        data_service,
        "last_price_sources",
        {"BTC-USD": "alpaca_crypto_snapshot", "ETH-USD": "alpaca_crypto_snapshot"},
    )

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         caplog.at_level(logging.WARNING, logger="src.monitor"):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 1.0], 1.0, 0.0, 0.0)
        mock_kf_get.return_value = mock_kf

        diagnostics = [
            await monitor.process_pair(pair, dict(latest_prices))
            for _ in range(CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT + 1)
        ]

    assert diagnostics[0]["reason"] == "below_entry_threshold"
    assert diagnostics[-1]["verdict"] == "IGNORED"
    assert diagnostics[-1]["reason"] == "stale_price_snapshot"
    assert mock_kf_get.await_count == CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT
    assert mock_save_state.await_count == CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT
    mock_orchestrator.assert_not_awaited()
    assert "PRICE STALENESS [BTC-USD/ETH-USD]" in caplog.text


@pytest.mark.asyncio
async def test_process_pair_blocks_repeated_alpaca_crypto_quote_mid_timestamp_before_kalman(monitor, monkeypatch, caplog):
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}
    monkeypatch.setattr(
        data_service,
        "last_price_sources",
        {"BTC-USD": "alpaca_crypto_quote_mid", "ETH-USD": "alpaca_crypto_quote_mid"},
    )
    monkeypatch.setattr(
        data_service,
        "last_price_timestamps",
        {
            "BTC-USD": "2026-05-20T12:01:00+00:00",
            "ETH-USD": "2026-05-20T12:01:00+00:00",
        },
        raising=False,
    )

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         caplog.at_level(logging.WARNING, logger="src.monitor"):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 1.0], 1.0, 0.0, 0.0)
        mock_kf_get.return_value = mock_kf

        diagnostics = [
            await monitor.process_pair(pair, dict(latest_prices))
            for _ in range(CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT + 1)
        ]

    assert diagnostics[0]["reason"] == "below_entry_threshold"
    assert diagnostics[-1]["verdict"] == "IGNORED"
    assert diagnostics[-1]["reason"] == "stale_price_snapshot"
    assert mock_kf_get.await_count == CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT
    assert mock_save_state.await_count == CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT
    mock_orchestrator.assert_not_awaited()
    assert "Alpaca crypto quote mid timestamps repeated" in caplog.text
