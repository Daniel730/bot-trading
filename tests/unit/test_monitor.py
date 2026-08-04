import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
import uuid
from src.config import settings
from src.services.persistence_service import ExitReason


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
async def test_take_profit_holds_when_friction_exceeds_gross_pnl(monitor):
    signal = {
        "signal_id": str(uuid.uuid4()),
        "legs": [
            {"ticker": "BTC-USD", "quantity": 0.01, "side": "BUY", "price": 60000.0},
            {"ticker": "ETH-USD", "quantity": 0.2, "side": "SELL", "price": 3000.0},
        ],
        "total_cost_basis": 1200.0,
    }

    with patch("src.monitor.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_prices, \
         patch("src.monitor.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_filter, \
         patch("src.monitor.estimate_round_trip_cost_pct", return_value=0.01), \
         patch.object(monitor, "_close_position", new_callable=AsyncMock) as mock_close, \
         patch("src.monitor.settings.TAKE_PROFIT_FORCE_EXIT_ZSCORE", 0.25):

        mock_prices.return_value = {"BTC-USD": 60100.0, "ETH-USD": 2990.0}
        kf = MagicMock()
        # Still in TP band (0.3) but above force-exit (0.25) and underwater on fees.
        kf.calculate_spread_and_zscore.return_value = (0.0, 0.3)
        mock_filter.return_value = kf

        await monitor._evaluate_exit_conditions(signal)

        mock_close.assert_not_awaited()


@pytest.mark.asyncio
async def test_take_profit_force_exits_when_mean_reversion_complete(monitor):
    signal = {
        "signal_id": str(uuid.uuid4()),
        "legs": [
            {"ticker": "BTC-USD", "quantity": 0.01, "side": "BUY", "price": 60000.0},
            {"ticker": "ETH-USD", "quantity": 0.2, "side": "SELL", "price": 3000.0},
        ],
        "total_cost_basis": 1200.0,
    }

    with patch("src.monitor.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_prices, \
         patch("src.monitor.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_filter, \
         patch("src.monitor.estimate_round_trip_cost_pct", return_value=0.01), \
         patch.object(monitor, "_close_position", new_callable=AsyncMock) as mock_close, \
         patch("src.monitor.settings.TAKE_PROFIT_FORCE_EXIT_ZSCORE", 0.25):

        # Slight positive but still below 1% friction on ~$1.2k notional.
        mock_prices.return_value = {"BTC-USD": 60100.0, "ETH-USD": 2990.0}
        kf = MagicMock()
        kf.calculate_spread_and_zscore.return_value = (0.0, 0.1)
        mock_filter.return_value = kf

        await monitor._evaluate_exit_conditions(signal)

        mock_close.assert_awaited_once()
        assert mock_close.await_args.kwargs["reason"] == ExitReason.TAKE_PROFIT


@pytest.mark.asyncio
async def test_take_profit_closes_when_gross_pnl_covers_friction(monitor):
    signal = {
        "signal_id": str(uuid.uuid4()),
        "legs": [
            {"ticker": "BTC-USD", "quantity": 0.01, "side": "BUY", "price": 60000.0},
            {"ticker": "ETH-USD", "quantity": 0.2, "side": "SELL", "price": 3000.0},
        ],
        "total_cost_basis": 1200.0,
    }

    with patch("src.monitor.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_prices, \
         patch("src.monitor.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_filter, \
         patch("src.monitor.estimate_round_trip_cost_pct", return_value=0.001), \
         patch.object(monitor, "_close_position", new_callable=AsyncMock) as mock_close:

        mock_prices.return_value = {"BTC-USD": 61000.0, "ETH-USD": 2900.0}
        kf = MagicMock()
        kf.calculate_spread_and_zscore.return_value = (0.0, 0.3)
        mock_filter.return_value = kf

        await monitor._evaluate_exit_conditions(signal)

        mock_close.assert_awaited_once_with(
            signal,
            61000.0,
            2900.0,
            reason=ExitReason.TAKE_PROFIT,
            prices_by_ticker={"BTC-USD": 61000.0, "ETH-USD": 2900.0},
        )


@pytest.mark.asyncio
async def test_take_profit_friction_hold_skips_spread_guard_bid_ask(monitor):
    """Exit friction-hold must not re-run entry spread-guard bid/ask checks."""
    signal = {
        "signal_id": str(uuid.uuid4()),
        "legs": [
            {"ticker": "BTC-USD", "quantity": 0.01, "side": "BUY", "price": 60000.0},
            {"ticker": "ETH-USD", "quantity": 0.2, "side": "SELL", "price": 3000.0},
        ],
        "total_cost_basis": 1200.0,
    }

    with patch("src.monitor.data_service.get_latest_price_async", new_callable=AsyncMock) as mock_prices, \
         patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.monitor.arbitrage_service.get_or_create_filter", new_callable=AsyncMock) as mock_filter, \
         patch("src.monitor.estimate_round_trip_cost_pct", return_value=0.01), \
         patch.object(monitor, "_close_position", new_callable=AsyncMock) as mock_close:

        mock_prices.return_value = {"BTC-USD": 60100.0, "ETH-USD": 2990.0}
        kf = MagicMock()
        kf.calculate_spread_and_zscore.return_value = (0.0, 0.3)
        mock_filter.return_value = kf

        await monitor._evaluate_exit_conditions(signal)

        mock_close.assert_not_awaited()
        mock_bid_ask.assert_not_awaited()


@pytest.mark.asyncio
async def test_initialize_pairs_benches_denylisted_both_orders(monitor, monkeypatch):
    benched: list[str] = []

    async def fake_active():
        return [
            {
                "id": "BCH-USD_BTC-USD",
                "ticker_a": "BCH-USD",
                "ticker_b": "BTC-USD",
                "hedge_ratio": 280.0,
                "is_cointegrated": True,
                "status": "Active",
            },
            {
                "id": "BTC-USD_ETH-USD",
                "ticker_a": "BTC-USD",
                "ticker_b": "ETH-USD",
                "hedge_ratio": 1.2,
                "is_cointegrated": True,
                "status": "Active",
            },
        ]

    async def fake_update(pair_id: str, status: str):
        assert status == "Benched"
        benched.append(pair_id)

    async def fake_filter(pairs, **_kwargs):
        return list(pairs), []

    async def empty_hist(*_a, **_k):
        return None

    monkeypatch.setattr(settings, "PAIR_DENYLIST", "BTC-USD_BCH-USD")
    monkeypatch.setattr(settings, "LIVE_CAPITAL_DANGER", False)
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "MAX_ACTIVE_PAIRS", 20)

    with patch(
        "src.services.persistence_service.persistence_service.get_active_trading_pairs",
        new=fake_active,
    ), patch(
        "src.services.persistence_service.persistence_service.update_pair_status",
        new=fake_update,
    ), patch(
        "src.monitor.filter_pair_universe",
        new=fake_filter,
    ), patch(
        "src.monitor.data_service.get_historical_data_async",
        new=empty_hist,
    ), patch(
        "src.monitor.dashboard_service.update",
        new_callable=AsyncMock,
    ):
        await monitor.initialize_pairs()

    assert "BCH-USD_BTC-USD" in benched
    assert all(p["id"] != "BCH-USD_BTC-USD" for p in monitor.active_pairs)
    assert all(p.get("ticker_a") != "BCH-USD" for p in monitor.active_pairs)


@pytest.mark.asyncio
async def test_auto_scout_promotes_when_enabled(monitor, monkeypatch):
    import asyncio

    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(float(seconds))
        if len(sleeps) >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(settings, "PAIR_DISCOVERY_ENABLED", True)
    monkeypatch.setattr(settings, "PAIR_DISCOVERY_AUTO_PROMOTE", True)
    monkeypatch.setattr(settings, "SCOUT_INITIAL_DELAY_SECONDS", 60)
    monkeypatch.setattr(settings, "SCOUT_INTERVAL_HOURS", 12)

    with patch("src.monitor.asyncio.sleep", fake_sleep), patch(
        "src.agents.portfolio_manager_agent.portfolio_manager.run_discovery",
        new_callable=AsyncMock,
    ) as mock_discover, patch.object(
        monitor, "_rotate_elite_pairs", new_callable=AsyncMock
    ) as mock_rotate:
        with pytest.raises(asyncio.CancelledError):
            await monitor._auto_scout_and_rotate_loop()

    mock_discover.assert_awaited_once()
    mock_rotate.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_scout_skips_promote_when_disabled(monitor, monkeypatch):
    import asyncio

    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(float(seconds))
        if len(sleeps) >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(settings, "PAIR_DISCOVERY_ENABLED", True)
    monkeypatch.setattr(settings, "PAIR_DISCOVERY_AUTO_PROMOTE", False)
    monkeypatch.setattr(settings, "SCOUT_INITIAL_DELAY_SECONDS", 60)
    monkeypatch.setattr(settings, "SCOUT_INTERVAL_HOURS", 12)

    with patch("src.monitor.asyncio.sleep", fake_sleep), patch(
        "src.agents.portfolio_manager_agent.portfolio_manager.run_discovery",
        new_callable=AsyncMock,
    ) as mock_discover, patch.object(
        monitor, "_rotate_elite_pairs", new_callable=AsyncMock
    ) as mock_rotate:
        with pytest.raises(asyncio.CancelledError):
            await monitor._auto_scout_and_rotate_loop()

    mock_discover.assert_awaited_once()
    mock_rotate.assert_not_awaited()
