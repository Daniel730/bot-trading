import pytest
import json
import logging
from unittest.mock import AsyncMock, patch, MagicMock
from src.monitor import ArbitrageMonitor
import uuid
from src.config import settings
from src.services.persistence_service import ExitReason, OrderStatus, persistence_service

@pytest.fixture
def monitor(monkeypatch):
    # We need to ensure monitor.brokerage is a mock
    with patch("src.services.brokerage_service.BrokerageService") as mock_broker_class:
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
        },
        {
            "pair_id": "KO_PEP",
            "ticker_a": "KO",
            "ticker_b": "PEP",
            "verdict": "IGNORED",
            "confidence": 0.0,
            "reason": "missing_price",
            "has_price_a": True,
            "has_price_b": False,
        },
    ]


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
async def test_execute_trade_success(monitor):
    """
    S-07: Test execute_trade path.
    """
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock) as mock_shadow, \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1) # low spread
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_shadow.return_value = [] # empty portfolio for simplicity
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 300.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "leg-b"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 2
        assert mock_log_trade.await_count == 4
        mock_log_journal.assert_awaited_once()
        assert mock_await_fill.await_count == 2
        mock_update_status.assert_not_awaited()

@pytest.mark.asyncio
async def test_execute_trade_success_marks_both_final_legs_open_pair(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock), \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 300.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "leg-b"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        final_rows = [
            call.args[0]
            for call in mock_log_trade.await_args_list
            if call.args[0]["metadata_json"].get("fill_snapshot")
        ]

        assert len(final_rows) == 2
        assert {row["ticker"]: row["status"] for row in final_rows} == {
            "AAPL": OrderStatus.OPEN_PAIR,
            "MSFT": OrderStatus.OPEN_PAIR,
        }


@pytest.mark.asyncio
async def test_execute_trade_blocks_duplicate_active_pair_before_broker_order(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.persistence_service.get_open_signals", new_callable=AsyncMock) as mock_open_signals, \
         patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock), \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock), \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False):

        mock_open_signals.return_value = [
            {
                "signal_id": str(uuid.uuid4()),
                "legs": [
                    {"ticker": "AAPL", "side": "BUY", "quantity": 1.0, "price": 150.0},
                    {"ticker": "MSFT", "side": "SELL", "quantity": 1.0, "price": 300.0},
                ],
            }
        ]
        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 300.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "leg-b"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        monitor.brokerage.place_value_order.assert_not_called()
        mock_notify.assert_awaited_once()
        assert "Duplicate entry blocked" in mock_notify.await_args.args[0]


@pytest.mark.asyncio
async def test_execute_trade_blocks_pending_pair_order_before_broker_order(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())
    monitor.brokerage.get_pending_orders = AsyncMock(
        return_value=[{"ticker": "AAPL", "id": "pending-a", "status": "accepted"}]
    )

    with patch("src.monitor.persistence_service.get_open_signals", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock), \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock), \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 300.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "leg-b"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        monitor.brokerage.place_value_order.assert_not_called()
        mock_notify.assert_awaited_once()
        assert "pending broker order" in mock_notify.await_args.args[0]


@pytest.mark.asyncio
async def test_execute_trade_marks_partial_exposure_when_leg_b_not_terminal(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock), \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
            None,
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "leg-b"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 2
        assert mock_await_fill.await_count == 2
        mock_notify.assert_awaited_once()

        partial_rows = [
            call.args[0]
            for call in mock_log_trade.await_args_list
            if call.args[0]["metadata_json"].get("pair_status") == OrderStatus.PARTIAL_EXPOSURE.value
        ]

        assert len(partial_rows) == 2
        assert {row["ticker"]: row["status"] for row in partial_rows} == {
            "AAPL": OrderStatus.PARTIAL_EXPOSURE,
            "MSFT": OrderStatus.PARTIAL_EXPOSURE,
        }
        assert {row["ticker"]: row["metadata_json"]["order_status"] for row in partial_rows} == {
            "AAPL": OrderStatus.LEG_A_FILLED.value,
            "MSFT": OrderStatus.LEG_B_SUBMITTED.value,
        }


@pytest.mark.asyncio
async def test_execute_trade_fails_closed_when_leg_b_partially_fills(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
            {"status": "partially_filled", "filled_qty": 0.25, "filled_avg_price": 300.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "leg-b"},
        ])

        result = await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert result == {"executed": False, "reason": OrderStatus.PARTIAL_EXPOSURE.value}
        assert monitor.brokerage.place_value_order.await_count == 2
        mock_await_fill.assert_any_await("leg-a", timeout=30)
        mock_await_fill.assert_any_await("leg-b", timeout=30)
        mock_update_status.assert_any_await(uuid.UUID(signal_id), OrderStatus.PARTIAL_EXPOSURE)
        mock_log_journal.assert_not_awaited()
        mock_notify.assert_awaited_once()
        assert "partially filled" in mock_notify.await_args.args[0]
        assert "manual reconciliation" in mock_notify.await_args.args[0].lower()

        partial_rows = [
            call.args[0]
            for call in mock_log_trade.await_args_list
            if call.args[0]["metadata_json"].get("pair_status") == OrderStatus.PARTIAL_EXPOSURE.value
        ]
        assert len(partial_rows) == 2
        rows_by_ticker = {row["ticker"]: row for row in partial_rows}
        assert rows_by_ticker["MSFT"]["quantity"] == 0.25
        assert rows_by_ticker["MSFT"]["metadata_json"]["order_status"] == OrderStatus.LEG_B_PARTIAL.value


@pytest.mark.asyncio
async def test_execute_trade_blocks_when_pending_orders_budget_read_fails(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.notification_service.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": False,
            "rejection_reason": "should not reach risk checks",
        }
        monitor.brokerage.get_pending_orders_value.side_effect = RuntimeError("pending read down")
        monitor.brokerage.place_value_order = AsyncMock()

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        mock_validate_trade.assert_not_called()
        monitor.brokerage.place_value_order.assert_not_called()
        mock_notify.assert_awaited_once()
        assert "pending-orders budget read failed" in mock_notify.await_args.args[0]


@pytest.mark.asyncio
async def test_execute_trade_blocks_when_account_balance_read_fails(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.notification_service.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        monitor.brokerage.get_account_cash.side_effect = RuntimeError("account read down")
        monitor.brokerage.place_value_order = AsyncMock()

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        mock_validate_trade.assert_not_called()
        monitor.brokerage.place_value_order.assert_not_called()
        mock_notify.assert_awaited_once()
        assert "account balance read failed" in mock_notify.await_args.args[0]


@pytest.mark.asyncio
async def test_await_order_fill_does_not_assume_missing_open_order_is_filled(monitor):
    monitor.brokerage.get_pending_orders = AsyncMock(return_value=[])
    monitor.brokerage.get_order = AsyncMock(return_value={})

    with patch("src.monitor.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await monitor._await_order_fill("order-missing", timeout=0.01)

    assert result is None
    monitor.brokerage.get_pending_orders.assert_awaited_once()
    monitor.brokerage.get_order.assert_awaited_once_with("order-missing")
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_trade_marks_manual_reconciliation_when_leg_a_submission_ambiguous(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.services.notification_service.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        monitor.brokerage.place_value_order = AsyncMock(return_value={
            "status": "unknown",
            "client_order_id": f"{signal_id}-A",
            "requires_reconciliation": True,
            "message": "submit timed out and reconciliation failed",
        })

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 1
        mock_await_fill.assert_not_awaited()
        mock_sleep.assert_not_awaited()
        mock_log_journal.assert_not_awaited()
        assert mock_log_trade.await_args.args[0]["status"] == OrderStatus.NEEDS_MANUAL_RECONCILIATION
        assert mock_log_trade.await_args.args[0]["order_id"] == f"{signal_id}-A"
        mock_update_status.assert_awaited_once_with(uuid.UUID(signal_id), OrderStatus.NEEDS_MANUAL_RECONCILIATION)
        mock_notify.assert_awaited_once()

@pytest.mark.parametrize(
    "leg_a_fill, expected_status",
    [
        (
            {"status": "rejected", "filled_qty": 0.0, "filled_avg_price": 0.0},
            OrderStatus.LEG_A_REJECTED,
        ),
        (
            {"status": "filled", "filled_qty": 0.0, "filled_avg_price": 0.0},
            OrderStatus.NEEDS_MANUAL_RECONCILIATION,
        ),
    ],
)
@pytest.mark.asyncio
async def test_execute_trade_blocks_leg_b_without_confirmed_leg_a_fill(
    monitor,
    leg_a_fill,
    expected_status,
):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.services.notification_service.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            leg_a_fill,
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 300.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "leg-b"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 1
        mock_await_fill.assert_awaited_once_with("leg-a", timeout=30)
        mock_sleep.assert_not_awaited()
        assert mock_log_trade.await_count == 1
        mock_log_journal.assert_not_awaited()
        mock_update_status.assert_awaited_once_with(uuid.UUID(signal_id), expected_status)
        mock_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_trade_blocks_leg_b_when_leg_a_filled_quantity_is_short(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.services.persistence_service.persistence_service.update_trade_fill", new_callable=AsyncMock, create=True) as mock_update_fill, \
         patch("src.services.notification_service.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 0.5, "filled_avg_price": 150.0},
            {"status": "filled", "filled_qty": 0.5, "filled_avg_price": 150.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "close-a"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 2
        close_call = monitor.brokerage.place_value_order.await_args_list[1]
        assert close_call.args[0] == "AAPL"
        assert close_call.args[1] == pytest.approx(75.0)
        assert close_call.args[2] == "BUY"
        assert close_call.kwargs["client_order_id"] == f"{signal_id}-A-PARTIAL-CLOSE"
        mock_await_fill.assert_any_await("leg-a", timeout=30)
        mock_await_fill.assert_any_await("close-a", timeout=30)
        mock_sleep.assert_not_awaited()
        assert mock_log_trade.await_count == 1
        mock_log_journal.assert_not_awaited()
        mock_update_fill.assert_awaited_once_with(
            uuid.UUID(signal_id),
            "leg-a",
            filled_quantity=0.5,
            fill_price=150.0,
            metadata_updates={
                "filled_qty": 0.5,
                "filled_avg_price": 150.0,
                "order_status": OrderStatus.PARTIAL_EXPOSURE.value,
                "fill_snapshot": {"status": "filled", "filled_qty": 0.5, "filled_avg_price": 150.0},
            },
        )
        mock_update_status.assert_any_await(
            uuid.UUID(signal_id),
            OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
        )
        mock_notify.assert_awaited_once()
        assert "filled_qty=0.5" in mock_notify.await_args.args[0]
        assert "expected_qty=" in mock_notify.await_args.args[0]


@pytest.mark.asyncio
async def test_execute_trade_emergency_closes_leg_a_when_leg_b_fails(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "error", "message": "leg b rejected"},
            {"status": "success", "order_id": "close-a"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 3
        assert mock_log_trade.await_count == 2
        mock_log_journal.assert_not_awaited()
        mock_await_fill.assert_any_await("leg-a", timeout=30)
        mock_await_fill.assert_any_await("close-a", timeout=30)
        mock_update_status.assert_any_await(
            uuid.UUID(signal_id),
            OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
        )
        orphan_rows = [
            call.args[0]
            for call in mock_log_trade.await_args_list
            if call.args[0].get("metadata_json", {}).get("orphaned")
        ]
        assert orphan_rows == []
        mock_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_trade_emergency_closes_leg_a_when_leg_b_fill_rejects_after_submit(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
            {"status": "rejected", "filled_qty": 0.0, "filled_avg_price": 0.0},
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "leg-b"},
            {"status": "success", "order_id": "close-a"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 3
        close_call = monitor.brokerage.place_value_order.await_args_list[2]
        assert close_call.args[0] == "AAPL"
        assert close_call.args[2] == "BUY"
        assert close_call.kwargs["client_order_id"] == f"{signal_id}-A-EMERGENCY-CLOSE"
        mock_await_fill.assert_any_await("leg-a", timeout=30)
        mock_await_fill.assert_any_await("leg-b", timeout=30)
        mock_await_fill.assert_any_await("close-a", timeout=30)
        mock_log_journal.assert_not_awaited()
        mock_update_status.assert_any_await(
            uuid.UUID(signal_id),
            OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
        )
        assert mock_log_trade.await_count == 2
        mock_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.return_value = {
            "status": "filled",
            "filled_qty": 1.0,
            "filled_avg_price": 150.0,
        }
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "error", "message": "leg b rejected"},
            {
                "status": "unknown",
                "order_id": "close-a",
                "requires_reconciliation": True,
                "message": "emergency close submit timed out",
            },
        ])

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 3
        mock_log_journal.assert_not_awaited()
        mock_update_status.assert_any_await(
            uuid.UUID(signal_id),
            OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
        )
        orphan_rows = [
            call.args[0]
            for call in mock_log_trade.await_args_list
            if call.args[0].get("metadata_json", {}).get("reason") == "emergency_close_unknown"
        ]
        assert len(orphan_rows) == 1
        assert orphan_rows[0]["status"] == OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION
        mock_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_trade_marks_manual_reconciliation_when_emergency_close_fill_unconfirmed(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
            None,
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "error", "message": "leg b rejected"},
            {"status": "success", "order_id": "close-a"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 3
        assert mock_await_fill.await_count == 2
        mock_await_fill.assert_any_await("leg-a", timeout=30)
        mock_await_fill.assert_any_await("close-a", timeout=30)
        mock_log_journal.assert_not_awaited()
        mock_update_status.assert_any_await(
            uuid.UUID(signal_id),
            OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
        )
        orphan_rows = [
            call.args[0]
            for call in mock_log_trade.await_args_list
            if call.args[0].get("metadata_json", {}).get("reason") == "emergency_close_unconfirmed"
        ]
        assert len(orphan_rows) == 1
        assert orphan_rows[0]["status"] == OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION
        mock_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_trade_marks_manual_reconciliation_when_emergency_close_partial_fill(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
            {"status": "filled", "filled_qty": 0.5, "filled_avg_price": 150.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "error", "message": "leg b rejected"},
            {"status": "success", "order_id": "close-a"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 3
        assert mock_await_fill.await_count == 2
        mock_await_fill.assert_any_await("leg-a", timeout=30)
        mock_await_fill.assert_any_await("close-a", timeout=30)
        mock_log_journal.assert_not_awaited()
        mock_update_status.assert_any_await(
            uuid.UUID(signal_id),
            OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
        )
        orphan_rows = [
            call.args[0]
            for call in mock_log_trade.await_args_list
            if call.args[0].get("metadata_json", {}).get("reason") == "emergency_close_unconfirmed"
        ]
        assert len(orphan_rows) == 1
        assert orphan_rows[0]["metadata_json"]["close_fill"]["filled_qty"] == 0.5
        assert orphan_rows[0]["status"] == OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION
        mock_notify.assert_awaited_once()
        assert "expected_qty=1.0" in mock_notify.await_args.args[0]


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
async def test_close_position_success(monitor):
    """
    S-07: Test _close_position path.
    """
    signal = {
        "signal_id": str(uuid.uuid4()),
        "legs": [
            {"ticker": "AAPL", "quantity": 10, "side": "BUY", "price": 150.0},
            {"ticker": "MSFT", "quantity": 5, "side": "SELL", "price": 300.0}
        ]
    }

    with patch("src.monitor.persistence_service") as mock_persistence, \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "DEV_MODE", False):
        mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
        mock_persistence.close_trade = AsyncMock()
        mock_persistence.update_signal_status = AsyncMock()
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "close-a"},
            {"status": "success", "order_id": "close-b"},
        ])
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 10.0, "filled_avg_price": 160.0},
            {"status": "filled", "filled_qty": 5.0, "filled_avg_price": 290.0},
        ]

        await monitor._close_position(signal, 160.0, 290.0, ExitReason.TAKE_PROFIT)

        assert monitor.brokerage.place_value_order.await_count == 2
        assert mock_await_fill.await_count == 2
        mock_persistence.close_trade.assert_awaited_once()

@pytest.mark.asyncio
async def test_close_position_does_not_close_ledger_until_all_close_orders_fill(monitor):
    signal_id = str(uuid.uuid4())
    signal = {
        "signal_id": signal_id,
        "legs": [
            {"ticker": "AAPL", "quantity": 10, "side": "BUY", "price": 150.0},
            {"ticker": "MSFT", "quantity": 5, "side": "SELL", "price": 300.0},
        ],
        "total_cost_basis": 3000.0,
    }

    with patch("src.monitor.persistence_service") as mock_persistence, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "DEV_MODE", False), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill:

        mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
        mock_persistence.close_trade = AsyncMock()
        mock_persistence.update_signal_status = AsyncMock()
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "close-a"},
            {"status": "success", "order_id": "close-b"},
        ])
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 10.0, "filled_avg_price": 160.0},
            None,
        ]

        await monitor._close_position(signal, 160.0, 290.0, ExitReason.TAKE_PROFIT)

        assert monitor.brokerage.place_value_order.await_count == 2
        assert mock_await_fill.await_count == 2
        mock_persistence.close_trade.assert_not_awaited()
        mock_persistence.update_signal_status.assert_awaited_once_with(
            uuid.UUID(signal_id),
            OrderStatus.NEEDS_MANUAL_RECONCILIATION,
        )
        mock_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_position_does_not_close_ledger_on_short_close_fill_quantity(monitor):
    signal_id = str(uuid.uuid4())
    signal = {
        "signal_id": signal_id,
        "legs": [
            {"ticker": "AAPL", "quantity": 10, "side": "BUY", "price": 150.0},
            {"ticker": "MSFT", "quantity": 5, "side": "SELL", "price": 300.0},
        ],
        "total_cost_basis": 3000.0,
    }

    with patch("src.monitor.persistence_service") as mock_persistence, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "DEV_MODE", False), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill:

        mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
        mock_persistence.close_trade = AsyncMock()
        mock_persistence.update_signal_status = AsyncMock()
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "close-a"},
            {"status": "success", "order_id": "close-b"},
        ])
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 10.0, "filled_avg_price": 160.0},
            {"status": "filled", "filled_qty": 2.5, "filled_avg_price": 290.0},
        ]

        await monitor._close_position(signal, 160.0, 290.0, ExitReason.TAKE_PROFIT)

        assert monitor.brokerage.place_value_order.await_count == 2
        assert mock_await_fill.await_count == 2
        mock_persistence.close_trade.assert_not_awaited()
        mock_persistence.update_signal_status.assert_awaited_once_with(
            uuid.UUID(signal_id),
            OrderStatus.NEEDS_MANUAL_RECONCILIATION,
        )
        mock_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_position_skips_sell_when_broker_has_no_shares(monitor):
    signal = {
        "signal_id": str(uuid.uuid4()),
        "legs": [
            {"ticker": "AAPL", "quantity": 10, "side": "BUY", "price": 150.0},
            {"ticker": "MSFT", "quantity": 5, "side": "SELL", "price": 300.0}
        ]
    }

    from src.services.persistence_service import ExitReason
    with patch("src.services.persistence_service.persistence_service.close_trade", new_callable=AsyncMock) as mock_close, \
         patch("src.services.persistence_service.persistence_service.mark_signal_closing_if_open", new_callable=AsyncMock, return_value=True) as mock_mark_closing, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch.object(settings, "PAPER_TRADING", False):
        monitor.brokerage.get_available_quantity.return_value = 0.0
        monitor.brokerage.place_value_order = AsyncMock(return_value={"status": "success"})

        await monitor._close_position(signal, 160.0, 290.0, ExitReason.TAKE_PROFIT)

        monitor.brokerage.place_value_order.assert_not_called()
        mock_mark_closing.assert_awaited_once_with(uuid.UUID(signal["signal_id"]))
        mock_close.assert_not_called()
        mock_update_status.assert_awaited_once_with(
            uuid.UUID(signal["signal_id"]),
            OrderStatus.OPEN,
        )
        mock_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_trade_paper_logs_entry_journal_before_shadow(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())
    call_order = []

    async def log_journal(payload):
        call_order.append(("journal", payload))

    async def execute_shadow(*args, **kwargs):
        call_order.append(("shadow", {"args": args, "kwargs": kwargs}))

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new=AsyncMock(side_effect=log_journal)) as mock_log_journal, \
         patch("src.services.shadow_service.shadow_service.execute_simulated_trade", new=AsyncMock(side_effect=execute_shadow)) as mock_shadow_exec, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(settings, "PAPER_TRADING", True):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {
            "regime": "STABLE",
            "confidence": 0.85,
            "features": {"volatility": 0.12},
        }

        result = await monitor.execute_trade(
            pair,
            "Short-Long",
            150.0,
            300.0,
            signal_id,
            entry_context={
                "z_score": 2.7,
                "entry_zscore": 2.2,
                "confidence": 0.81,
                "orchestrator_verdict": "APPROVE",
            },
        )

    assert result == {"executed": True, "reason": "paper_shadow_executed"}
    assert [name for name, _ in call_order] == ["journal", "shadow"]
    mock_log_journal.assert_awaited_once()
    mock_shadow_exec.assert_awaited_once()

    journal_payload = call_order[0][1]
    assert journal_payload["signal_id"] == uuid.UUID(signal_id)
    assert journal_payload["entry_regime"] == "STABLE"
    metrics = journal_payload["metrics_at_entry"]
    assert metrics["z_score"] == 2.7
    assert metrics["entry_zscore"] == 2.2
    assert metrics["confidence"] == 0.81
    assert metrics["orchestrator_verdict"] == "APPROVE"
    assert metrics["win_prob"] == settings.DEFAULT_WIN_PROBABILITY
    assert metrics["regime_confidence"] == 0.85
    assert metrics["features"] == {"volatility": 0.12}
    assert metrics["gross_notional"] == pytest.approx(299.98)
    assert metrics["leg_a_notional"] == pytest.approx(99.99)
    assert metrics["leg_b_notional"] == pytest.approx(199.99)
    assert metrics["hedge_ratio"] == 1.0
    assert metrics["kelly_fraction"] == 0.1
    assert metrics["sizing_base"] == 10_000.0
    assert metrics["max_allowed_fiat"] == 300.0
    assert metrics["direction"] == "Short-Long"
    assert metrics["paper_trade"] is True

@pytest.mark.asyncio
async def test_execute_trade_crypto_live_uses_broker(monitor):
    pair = {"ticker_a": "ETH-USD", "ticker_b": "BTC-USD", "id": "ETH-USD_BTC-USD"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.shadow_service.shadow_service.execute_simulated_trade", new_callable=AsyncMock) as mock_shadow_exec, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock) as mock_shadow_portfolio, \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=250.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 250.0, "used": 0.0, "remaining": 250.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False):

        mock_bid_ask.return_value = (100.0, 100.05)
        mock_shadow_portfolio.return_value = []
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 100.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 100.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 0.01, "filled_avg_price": 2000.0},
            {"status": "filled", "filled_qty": 0.001, "filled_avg_price": 50000.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "crypto-leg-a"},
            {"status": "success", "order_id": "crypto-leg-b"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 2000.0, 50000.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 2
        monitor.brokerage.get_account_cash.assert_called_once()
        mock_shadow_exec.assert_not_called()
        assert mock_log_trade.await_count == 4
        mock_log_journal.assert_awaited_once()
        assert mock_await_fill.await_count == 2

@pytest.mark.asyncio
async def test_execute_trade_crypto_budget_cap_applied(monitor):
    pair = {"ticker_a": "ETH-USD", "ticker_b": "BTC-USD", "id": "ETH-USD_BTC-USD"}
    signal_id = str(uuid.uuid4())

    with patch("src.services.data_service.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=250.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 250.0, "used": 0.0, "remaining": 250.0}), \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock), \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock), \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "ALPACA_BUDGET_USD", 250.0):

        mock_bid_ask.return_value = (100.0, 100.05)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 100.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 100.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        monitor.brokerage.get_account_cash.return_value = 1200.0
        monitor.brokerage.get_account_equity.return_value = 1200.0
        monitor.brokerage.get_account_buying_power.return_value = 1200.0
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 0.01, "filled_avg_price": 2000.0},
            {"status": "filled", "filled_qty": 0.001, "filled_avg_price": 50000.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "crypto-leg-a"},
            {"status": "success", "order_id": "crypto-leg-b"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 2000.0, 50000.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 2
        assert mock_await_fill.await_count == 2
        assert mock_validate_trade.call_count == 1
        assert mock_validate_trade.call_args.kwargs["total_portfolio_cash"] == 1200.0

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
        )

        diagnostic = await monitor.process_pair(pair, latest_prices)

        assert diagnostic["verdict"] == "VETOED"
        assert diagnostic["confidence"] == 0.8
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
