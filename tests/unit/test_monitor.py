import pytest
import json
import logging
from unittest.mock import AsyncMock, patch, MagicMock
from src.monitor import ArbitrageMonitor, CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT
import uuid
from src.config import settings
from src.services.data_service import data_service
from src.services.persistence_service import ExitReason, OrderStatus, persistence_service


def test_crypto_snapshot_stale_repeat_limit_matches_runtime_cadence():
    assert CRYPTO_SNAPSHOT_STALE_REPEAT_LIMIT == 5


@pytest.fixture
def monitor(monkeypatch):
    # We need to ensure monitor.brokerage is a mock
    with patch("src.monitor.BrokerageService") as mock_broker_class:
        monkeypatch.setattr(persistence_service, "get_open_signals", AsyncMock(return_value=[]))
        m = ArbitrageMonitor(mode="live")
        # Ensure the instance created inside __init__ is our mock
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


def test_trade_decision_report_appends_cycle_jsonl(monitor, tmp_path, monkeypatch):
    report_path = tmp_path / "trade_decision_reports.jsonl"
    monkeypatch.setattr(monitor, "trade_decision_report_path", report_path, raising=False)
    monkeypatch.setattr(settings, "PAPER_TRADING", True)
    monitor.active_pairs = [
        {"id": "AAPL_MSFT", "ticker_a": "AAPL", "ticker_b": "MSFT"},
        {"id": "KO_PEP", "ticker_a": "KO", "ticker_b": "PEP"},
    ]

    monitor._write_trade_decision_report(
        scan_pairs=monitor.active_pairs,
        results=[
            {"verdict": "EXECUTED", "confidence": 0.92},
            {"verdict": "IGNORED", "confidence": 0.0, "reason": "missing_price"},
        ],
        latest_prices={"AAPL": 150.0, "MSFT": 300.0, "KO": 80.0},
        open_signals=[{"signal_id": "open-1"}],
        active_signal_count=1,
        vetoed_count=0,
        sizing_base=10_000.0,
    )

    report = json.loads(report_path.read_text(encoding="utf-8").strip())

    assert report["mode"] == "paper"
    assert report["pairs_loaded"] == 2
    assert report["pairs_scanned"] == 2
    assert report["prices_received"] == 3
    assert report["signals"] == 1
    assert report["vetoed"] == 0
    assert report["open_positions"] == 1
    assert report["sizing_base"] == 10_000.0
    assert report["decisions"] == [
        {
            "pair_id": "AAPL_MSFT",
            "ticker_a": "AAPL",
            "ticker_b": "MSFT",
            "verdict": "EXECUTED",
            "confidence": 0.92,
            "has_price_a": True,
            "has_price_b": True,
            "price_a": 150.0,
            "price_b": 300.0,
            "price_source_a": "unknown",
            "price_source_b": "unknown",
            "price_timestamp_a": None,
            "price_timestamp_b": None,
        },
        {
            "pair_id": "KO_PEP",
            "ticker_a": "KO",
            "ticker_b": "PEP",
            "verdict": "IGNORED",
            "confidence": 0.0,
            "reason": "missing_price",
            "rejection_reason": "missing_price",
            "has_price_a": True,
            "has_price_b": False,
            "price_a": 80.0,
            "price_b": None,
            "price_source_a": "unknown",
            "price_source_b": None,
            "price_timestamp_a": None,
            "price_timestamp_b": None,
        },
    ]


def test_trade_decision_report_includes_loaded_pairs_not_scanned(monitor, tmp_path, monkeypatch):
    report_path = tmp_path / "trade_decision_reports.jsonl"
    monkeypatch.setattr(monitor, "trade_decision_report_path", report_path, raising=False)
    monkeypatch.setattr(monitor, "is_market_open", MagicMock(return_value=False))
    monitor.active_pairs = [
        {"id": "AAPL_MSFT", "ticker_a": "AAPL", "ticker_b": "MSFT"},
        {"id": "BTC-USD_ETH-USD", "ticker_a": "BTC-USD", "ticker_b": "ETH-USD"},
    ]

    monitor._write_trade_decision_report(
        scan_pairs=[monitor.active_pairs[1]],
        results=[{"verdict": "IGNORED", "confidence": 0.0, "reason": "below_entry_threshold"}],
        latest_prices={"BTC-USD": 90_000.0, "ETH-USD": 3_000.0},
        open_signals=[],
        active_signal_count=0,
        vetoed_count=0,
        sizing_base=10_000.0,
    )

    report = json.loads(report_path.read_text(encoding="utf-8").strip())

    assert report["pairs_loaded"] == 2
    assert report["pairs_scanned"] == 1
    assert report["decisions"] == [
        {
            "pair_id": "BTC-USD_ETH-USD",
            "ticker_a": "BTC-USD",
            "ticker_b": "ETH-USD",
            "verdict": "IGNORED",
            "confidence": 0.0,
            "reason": "below_entry_threshold",
            "rejection_reason": "below_entry_threshold",
            "has_price_a": True,
            "has_price_b": True,
            "price_a": 90_000.0,
            "price_b": 3_000.0,
            "price_source_a": "unknown",
            "price_source_b": "unknown",
            "price_timestamp_a": None,
            "price_timestamp_b": None,
        },
        {
            "pair_id": "AAPL_MSFT",
            "ticker_a": "AAPL",
            "ticker_b": "MSFT",
            "verdict": "IGNORED",
            "confidence": 0.0,
            "reason": "market_closed",
            "rejection_reason": "market_closed",
            "has_price_a": False,
            "has_price_b": False,
            "price_a": None,
            "price_b": None,
            "price_source_a": None,
            "price_source_b": None,
            "price_timestamp_a": None,
            "price_timestamp_b": None,
        },
    ]


def test_trade_decision_report_includes_price_source_and_rejection_details(monitor, tmp_path, monkeypatch):
    report_path = tmp_path / "trade_decision_reports.jsonl"
    monkeypatch.setattr(monitor, "trade_decision_report_path", report_path, raising=False)

    monitor._write_trade_decision_report(
        scan_pairs=[
            {"id": "BTC-USD_ETH-USD", "ticker_a": "BTC-USD", "ticker_b": "ETH-USD"},
        ],
        results=[
            {"verdict": "IGNORED", "confidence": 0.0, "reason": "price_sanity_invalid"},
        ],
        latest_prices={"BTC-USD": 9.45, "ETH-USD": 2110.0},
        latest_price_sources={"BTC-USD": "yfinance", "ETH-USD": "alpaca_crypto_snapshot"},
        open_signals=[],
        active_signal_count=0,
        vetoed_count=0,
        sizing_base=10_000.0,
    )

    report = json.loads(report_path.read_text(encoding="utf-8").strip())
    decision = report["decisions"][0]

    assert decision["price_a"] == 9.45
    assert decision["price_b"] == 2110.0
    assert decision["price_source_a"] == "yfinance"
    assert decision["price_source_b"] == "alpaca_crypto_snapshot"
    assert decision["rejection_reason"] == "price_sanity_invalid"


def test_trade_decision_report_includes_price_timestamps(monitor, tmp_path, monkeypatch):
    report_path = tmp_path / "trade_decision_reports.jsonl"
    monkeypatch.setattr(monitor, "trade_decision_report_path", report_path, raising=False)

    monitor._write_trade_decision_report(
        scan_pairs=[
            {"id": "BTC-USD_ETH-USD", "ticker_a": "BTC-USD", "ticker_b": "ETH-USD"},
        ],
        results=[
            {"verdict": "IGNORED", "confidence": 0.0, "reason": "stale_price_snapshot"},
        ],
        latest_prices={"BTC-USD": 90105.0, "ETH-USD": 2130.0},
        latest_price_sources={
            "BTC-USD": "alpaca_crypto_quote_mid",
            "ETH-USD": "alpaca_crypto_quote_mid",
        },
        latest_price_timestamps={
            "BTC-USD": "2026-05-20T12:01:00+00:00",
            "ETH-USD": "2026-05-20T12:01:03+00:00",
        },
        open_signals=[],
        active_signal_count=0,
        vetoed_count=0,
        sizing_base=10_000.0,
    )

    report = json.loads(report_path.read_text(encoding="utf-8").strip())
    decision = report["decisions"][0]

    assert decision["price_timestamp_a"] == "2026-05-20T12:01:00+00:00"
    assert decision["price_timestamp_b"] == "2026-05-20T12:01:03+00:00"
    assert decision["price_source_a"] == "alpaca_crypto_quote_mid"
    assert decision["price_source_b"] == "alpaca_crypto_quote_mid"


def test_trade_decision_report_includes_spread_guard_details(monitor, tmp_path, monkeypatch):
    report_path = tmp_path / "trade_decision_reports.jsonl"
    monkeypatch.setattr(monitor, "trade_decision_report_path", report_path, raising=False)

    monitor._write_trade_decision_report(
        scan_pairs=[
            {"id": "AAPL_MSFT", "ticker_a": "AAPL", "ticker_b": "MSFT"},
        ],
        results=[
            {
                "verdict": "EXECUTION_BLOCKED",
                "confidence": 0.8,
                "reason": "spread_guard",
                "bid_a": 100.0,
                "ask_a": 100.2,
                "bid_b": 50.0,
                "ask_b": 50.1,
                "spread_a_pct": 0.2,
                "spread_b_pct": 0.2,
                "total_spread_pct": 0.4004,
                "max_spread_pct": 0.3,
            },
        ],
        latest_prices={"AAPL": 100.2, "MSFT": 50.1},
        open_signals=[],
        active_signal_count=1,
        vetoed_count=0,
        sizing_base=10_000.0,
    )

    report = json.loads(report_path.read_text(encoding="utf-8").strip())
    decision = report["decisions"][0]

    assert decision["rejection_reason"] == "spread_guard"
    assert decision["bid_a"] == 100.0
    assert decision["ask_a"] == 100.2
    assert decision["bid_b"] == 50.0
    assert decision["ask_b"] == 50.1
    assert decision["spread_a_pct"] == 0.2
    assert decision["spread_b_pct"] == 0.2
    assert decision["total_spread_pct"] == 0.4004
    assert decision["max_spread_pct"] == 0.3


def test_trade_decision_report_includes_profit_guard_details(monitor, tmp_path, monkeypatch):
    report_path = tmp_path / "trade_decision_reports.jsonl"
    monkeypatch.setattr(monitor, "trade_decision_report_path", report_path, raising=False)

    monitor._write_trade_decision_report(
        scan_pairs=[
            {"id": "BTC-USD_ETH-USD", "ticker_a": "BTC-USD", "ticker_b": "ETH-USD"},
        ],
        results=[
            {
                "verdict": "VETOED",
                "confidence": 0.7,
                "reason": "unprofitable",
                "profit_guard_net_profit": -1.82,
                "profit_guard_gross_profit": 0.44,
                "profit_guard_friction_usd": 2.26,
                "profit_guard_friction_pct": 0.00125,
                "profit_guard_gross_notional": 1808.0,
                "profit_guard_spread_capture": 2.5,
                "profit_guard_z_score": 3.143,
            },
        ],
        latest_prices={"BTC-USD": 77540.48, "ETH-USD": 2131.16},
        latest_price_sources={
            "BTC-USD": "alpaca_crypto_snapshot",
            "ETH-USD": "alpaca_crypto_snapshot",
        },
        open_signals=[],
        active_signal_count=1,
        vetoed_count=1,
        sizing_base=985590.85,
    )

    report = json.loads(report_path.read_text(encoding="utf-8").strip())
    decision = report["decisions"][0]

    assert decision["rejection_reason"] == "unprofitable"
    assert decision["profit_guard_net_profit"] == -1.82
    assert decision["profit_guard_gross_profit"] == 0.44
    assert decision["profit_guard_friction_usd"] == 2.26
    assert decision["profit_guard_friction_pct"] == 0.00125
    assert decision["profit_guard_gross_notional"] == 1808.0
    assert decision["profit_guard_spread_capture"] == 2.5
    assert decision["profit_guard_z_score"] == 3.143


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


@pytest.mark.asyncio
async def test_process_pair_blocks_clipped_kalman_state_before_orchestrator(monitor, caplog):
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.monitor.redis_service.client.delete", new_callable=AsyncMock), \
         caplog.at_level(logging.WARNING, logger="src.monitor"):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 0.001], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf
        mock_orchestrator.return_value = {"final_confidence": 0.3, "final_verdict": "VETO"}

        diagnostic = await monitor.process_pair(pair, latest_prices)

    assert diagnostic["verdict"] == "IGNORED"
    assert diagnostic["reason"] == "kalman_state_invalid"
    mock_save_state.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()
    assert "KALMAN GUARD [BTC-USD/ETH-USD]" in caplog.text


@pytest.mark.asyncio
async def test_process_pair_quarantines_invalid_kalman_state_until_rebuild(monitor):
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    latest_prices = {"BTC-USD": 76800.0, "ETH-USD": 2110.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.monitor.redis_service.client.delete", new_callable=AsyncMock):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 0.001], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf
        mock_orchestrator.return_value = {"final_confidence": 0.3, "final_verdict": "VETO"}

        first = await monitor.process_pair(pair, latest_prices)
        second = await monitor.process_pair(pair, latest_prices)

    assert first["reason"] == "kalman_state_invalid"
    assert second["reason"] == "kalman_state_quarantined"
    assert mock_kf_get.await_count == 1
    mock_save_state.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()


@pytest.mark.asyncio
async def test_quarantined_kalman_state_requests_post_scan_rebuild(monitor):
    pair = {"ticker_a": "BTC-USD", "ticker_b": "LTC-USD", "id": "BTC-USD_LTC-USD"}
    latest_prices = {"BTC-USD": 76800.0, "LTC-USD": 85.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock) as mock_save_state, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.monitor.redis_service.client.delete", new_callable=AsyncMock):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0.0, 0.001], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf

        diagnostic = await monitor.process_pair(pair, latest_prices)

    assert diagnostic["reason"] == "kalman_state_invalid"
    assert monitor._kalman_quarantine_reload_requested is True
    mock_save_state.assert_not_awaited()
    mock_orchestrator.assert_not_awaited()

    monitor.reload_pairs = AsyncMock()

    rebuilt = await monitor._reload_quarantined_pairs_if_requested()

    assert rebuilt is True
    monitor.reload_pairs.assert_awaited_once()
    assert monitor._kalman_quarantine_reload_requested is False



@pytest.mark.asyncio
async def test_financial_kill_switch_uses_directional_pair_pnl(monitor):
    signal = {
        "signal_id": str(uuid.uuid4()),
        "legs": [
            {"ticker": "AAPL", "quantity": 10, "side": "SELL", "price": 100.0},
            {"ticker": "MSFT", "quantity": 10, "side": "BUY", "price": 100.0},
        ],
        "total_cost_basis": 2000.0,
    }

    with patch("src.monitor.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_prices, \
         patch("src.monitor.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_filter, \
         patch.object(monitor, "_close_position", new_callable=AsyncMock) as mock_close:

        mock_prices.return_value = {"AAPL": 120.0, "MSFT": 100.0}
        kf = MagicMock()
        kf.calculate_spread_and_zscore.return_value = (0.0, 1.0)
        mock_filter.return_value = kf

        await monitor._evaluate_exit_conditions(signal)

        mock_close.assert_awaited_once_with(
            signal,
            120.0,
            100.0,
            reason=ExitReason.KILL_SWITCH,
            prices_by_ticker={"AAPL": 120.0, "MSFT": 100.0},
        )
        mock_filter.assert_not_awaited()


@pytest.mark.asyncio
async def test_orchestrator_veto(monitor):
    """
    S-07: Test orchestrator veto path in process_pair.
    """
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0, "MSFT": 300.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock) as mock_audit, \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.monitor.estimate_pair_profit") as mock_estimate_profit, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch.object(monitor, "is_market_open", return_value=True):

        mock_kf = MagicMock()
        # New signature: (state, innovation_variance, z_score, spread)
        mock_kf.update.return_value = ([0, 1.0], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf

        # Orchestrator VETO (confidence < 0.5)
        mock_orchestrator.return_value = {"final_confidence": 0.3, "final_verdict": "VETO"}
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
            "fee_status": {"total_friction_percent": 0.0},
        }
        mock_estimate_profit.return_value = MagicMock(
            net_profit=10.0,
            profit_margin_pct=0.03,
            gross_profit=12.0,
            expected_loss=8.0,
            loss_margin_pct=0.02,
            friction_usd=2.0,
        )

        diagnostic = await monitor.process_pair(pair, latest_prices)

        assert diagnostic["verdict"] == "VETOED"
        assert diagnostic["confidence"] == 0.3
        mock_audit.assert_called_once()


@pytest.mark.asyncio
async def test_process_pair_low_confidence_veto_precedes_profit_guard(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0, "MSFT": 300.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.monitor.estimate_pair_profit") as mock_estimate_profit, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch.object(monitor, "is_market_open", return_value=True), \
         patch.object(settings, "MONITOR_MIN_AI_CONFIDENCE", 0.5):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0, 1.0], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf
        mock_orchestrator.return_value = {"final_confidence": 0.3, "final_verdict": "VETO"}

        diagnostic = await monitor.process_pair(pair, latest_prices)

        assert diagnostic["verdict"] == "VETOED"
        assert diagnostic["confidence"] == 0.3
        mock_validate_trade.assert_not_called()
        mock_estimate_profit.assert_not_called()
        assert monitor.active_signals[-1]["status"] == "VETOED"
        assert monitor.active_signals[-1]["confidence"] == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_process_pair_unprofitable_veto_preserves_confidence(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0, "MSFT": 300.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.monitor.estimate_pair_profit") as mock_estimate_profit, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch.object(monitor, "is_market_open", return_value=True), \
         patch.object(settings, "MONITOR_MIN_AI_CONFIDENCE", 0.5):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0, 1.0], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf
        mock_orchestrator.return_value = {"final_confidence": 0.8, "final_verdict": "APPROVE"}
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
            "fee_status": {"total_friction_percent": 0.002},
        }
        mock_estimate_profit.return_value = MagicMock(
            net_profit=-0.25,
            profit_margin_pct=-0.01,
            gross_profit=0.25,
            expected_loss=8.0,
            loss_margin_pct=0.02,
            friction_usd=0.5,
            spread_capture=0.75,
            stop_spread_move=12.0,
        )

        diagnostic = await monitor.process_pair(pair, latest_prices)

        assert diagnostic["verdict"] == "VETOED"
        assert diagnostic["confidence"] == 0.8
        assert diagnostic["profit_guard_net_profit"] == -0.25
        assert diagnostic["profit_guard_gross_profit"] == 0.25
        assert diagnostic["profit_guard_friction_usd"] == 0.5
        assert diagnostic["profit_guard_friction_pct"] == 0.002
        assert diagnostic["profit_guard_gross_notional"] == pytest.approx(299.98)
        assert diagnostic["profit_guard_quantity_a"] == pytest.approx(0.666666)
        assert diagnostic["profit_guard_quantity_b"] == pytest.approx(0.666666)
        assert diagnostic["profit_guard_z_score"] == 3.0
        assert monitor.active_signals[-1]["status"] == "VETOED_UNPROFITABLE"
        assert monitor.active_signals[-1]["confidence"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_process_pair_does_not_mark_failed_execution_as_executed(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    latest_prices = {"AAPL": 150.0, "MSFT": 300.0}

    with patch("src.services.arbitrage_service.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_kf_get, \
         patch("src.agents.orchestrator.orchestrator.ainvoke", new_callable=AsyncMock) as mock_orchestrator, \
         patch("src.services.audit_service.audit_service.log_thought_process", new_callable=AsyncMock), \
         patch("src.services.notification_service.notification_service.request_approval", new_callable=AsyncMock, return_value=True), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.monitor.estimate_pair_profit") as mock_estimate_profit, \
         patch("src.services.arbitrage_service.arbitrage_service.save_filter_state", new_callable=AsyncMock), \
         patch.object(monitor, "execute_trade", new_callable=AsyncMock) as mock_execute_trade, \
         patch.object(monitor, "is_market_open", return_value=True), \
         patch.object(settings, "MONITOR_MIN_AI_CONFIDENCE", 0.5):

        mock_kf = MagicMock()
        mock_kf.update.return_value = ([0, 1.0], 0.1, 3.0, 0.5)
        mock_kf_get.return_value = mock_kf
        mock_orchestrator.return_value = {"final_confidence": 0.8, "final_verdict": "APPROVE"}
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
            "fee_status": {"total_friction_percent": 0.0},
        }
        mock_estimate_profit.return_value = MagicMock(
            net_profit=10.0,
            profit_margin_pct=0.03,
            gross_profit=12.0,
            expected_loss=8.0,
            loss_margin_pct=0.02,
            friction_usd=2.0,
        )
        mock_execute_trade.return_value = {
            "executed": False,
            "reason": "duplicate_active_pair",
        }

        diagnostic = await monitor.process_pair(pair, latest_prices)

        assert diagnostic["verdict"] == "EXECUTION_BLOCKED"
        assert monitor.active_signals[-1]["status"] == "EXECUTION_BLOCKED"
        assert mock_execute_trade.await_count == 1
