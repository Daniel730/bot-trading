import pytest
from unittest.mock import AsyncMock, patch
import uuid
from src.config import settings
from src.services.persistence_service import OrderStatus

@pytest.mark.asyncio
async def test_execute_trade_success(monitor):
    """
    S-07: Test execute_trade path.
    """
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.services.persistence_service.persistence_service.update_trade_fill", new_callable=AsyncMock) as mock_update_fill, \
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
        assert mock_log_trade.await_count == 2
        assert mock_update_fill.await_count == 2
        mock_log_journal.assert_awaited_once()
        assert mock_await_fill.await_count == 2
        mock_update_status.assert_not_awaited()

@pytest.mark.asyncio
async def test_execute_trade_success_marks_both_final_legs_open_pair(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.update_trade_fill", new_callable=AsyncMock) as mock_update_fill, \
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

        # F-007: pre-submit ORDER_SUBMITTED for Leg A; Leg B still logged after place.
        statuses = [call.args[0]["status"] for call in mock_log_trade.await_args_list]
        assert OrderStatus.ORDER_SUBMITTED in statuses
        assert OrderStatus.LEG_B_SUBMITTED in statuses
        assert mock_update_fill.await_count == 2
        assert all(call.kwargs["status"] == OrderStatus.OPEN_PAIR for call in mock_update_fill.await_args_list)


@pytest.mark.asyncio
async def test_execute_trade_success_resolves_submitted_ledger_rows(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.update_trade_fill", new_callable=AsyncMock) as mock_update_fill, \
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

        statuses = [call.args[0]["status"] for call in mock_log_trade.await_args_list]
        assert OrderStatus.ORDER_SUBMITTED in statuses
        assert OrderStatus.LEG_B_SUBMITTED in statuses
        assert [call.args[1] for call in mock_update_fill.await_args_list] == ["leg-a", "leg-b"]
        assert [call.kwargs["status"] for call in mock_update_fill.await_args_list] == [
            OrderStatus.OPEN_PAIR,
            OrderStatus.OPEN_PAIR,
        ]


@pytest.mark.asyncio
async def test_execute_trade_blocks_duplicate_active_pair_before_broker_order(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.persistence_service.get_open_signals", new_callable=AsyncMock) as mock_open_signals, \
         patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
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
         patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
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
async def test_execute_trade_marks_manual_reconciliation_when_leg_b_not_terminal(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock), \
         patch("src.services.persistence_service.persistence_service.update_trade_fill", new_callable=AsyncMock) as mock_update_fill, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
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

        result = await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert result == {"executed": False, "reason": "leg_b_fill_timeout"}
        assert monitor.brokerage.place_value_order.await_count == 2
        assert mock_await_fill.await_count == 2
        mock_notify.assert_awaited_once()
        assert "NEEDS_MANUAL_RECONCILIATION" in mock_notify.await_args.args[0]
        mock_update_fill.assert_awaited_once()
        assert mock_update_fill.await_args.args[1] == "leg-a"
        assert mock_update_fill.await_args.kwargs["filled_quantity"] == 1.0
        assert mock_update_fill.await_args.kwargs["status"] == OrderStatus.NEEDS_MANUAL_RECONCILIATION
        assert (
            mock_update_fill.await_args.kwargs["metadata_updates"]["pair_status"]
            == OrderStatus.NEEDS_MANUAL_RECONCILIATION.value
        )
        mock_update_status.assert_awaited_once_with(
            uuid.UUID(signal_id),
            OrderStatus.NEEDS_MANUAL_RECONCILIATION,
        )


@pytest.mark.asyncio
async def test_execute_trade_fails_closed_when_leg_b_partially_fills(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.services.persistence_service.persistence_service.update_trade_fill", new_callable=AsyncMock) as mock_update_fill, \
         patch("src.services.persistence_service.persistence_service.close_trade", new_callable=AsyncMock) as mock_close_trade, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 0.0):

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
            {"status": "filled", "filled_qty": 0.25, "filled_avg_price": 300.0},
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "leg-b"},
            {"status": "success", "order_id": "close-b"},
            {"status": "success", "order_id": "close-a"},
        ])

        result = await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert result == {"executed": False, "reason": "leg_b_not_fully_filled"}
        assert monitor.brokerage.place_value_order.await_count == 4
        close_b_call = monitor.brokerage.place_value_order.await_args_list[2]
        assert close_b_call.kwargs["client_order_id"] == f"{signal_id}-B-PARTIAL-CLOSE"
        assert close_b_call.args[1] == pytest.approx(75.0)
        close_a_call = monitor.brokerage.place_value_order.await_args_list[3]
        assert close_a_call.kwargs["client_order_id"] == f"{signal_id}-A-EMERGENCY-CLOSE"
        # Emergency close must unwind the actual Leg A fill, not the plan notional.
        assert close_a_call.args[1] == pytest.approx(150.0)
        mock_await_fill.assert_any_await("leg-a", timeout=30)
        mock_await_fill.assert_any_await("leg-b", timeout=30)
        mock_update_status.assert_any_await(uuid.UUID(signal_id), OrderStatus.PARTIAL_EXPOSURE)
        mock_log_journal.assert_not_awaited()
        mock_close_trade.assert_awaited()
        mock_notify.assert_awaited()
        assert any("not confirmed as a full fill" in call.args[0] for call in mock_notify.await_args_list)

        partial_rows = [
            call
            for call in mock_update_fill.await_args_list
            if call.kwargs.get("status") == OrderStatus.PARTIAL_EXPOSURE
            or call.kwargs["metadata_updates"].get("pair_status") == OrderStatus.PARTIAL_EXPOSURE.value
        ]
        assert len(partial_rows) >= 2
        rows_by_order = {call.args[1]: call for call in partial_rows}
        assert rows_by_order["leg-b"].kwargs["filled_quantity"] == 0.25
        assert rows_by_order["leg-b"].kwargs["metadata_updates"]["order_status"] == OrderStatus.LEG_B_PARTIAL.value


@pytest.mark.asyncio
async def test_execute_trade_blocks_open_pair_when_leg_b_filled_quantity_is_short(monitor):
    """status=filled with severe shortfall must not open an imbalanced pair."""
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock), \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.services.persistence_service.persistence_service.update_trade_fill", new_callable=AsyncMock) as mock_update_fill, \
         patch("src.services.persistence_service.persistence_service.close_trade", new_callable=AsyncMock) as mock_close_trade, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock), \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 0.0):

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
            # Broker labeled filled but only half the planned Leg B size.
            {"status": "filled", "filled_qty": 0.333333, "filled_avg_price": 300.0},
            {"status": "filled", "filled_qty": 0.333333, "filled_avg_price": 300.0},
            {"status": "filled", "filled_qty": 1.0, "filled_avg_price": 150.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "leg-b"},
            {"status": "success", "order_id": "close-b"},
            {"status": "success", "order_id": "close-a"},
        ])

        result = await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert result["executed"] is False
        assert result["reason"] == "leg_b_not_fully_filled"
        mock_log_journal.assert_not_awaited()
        mock_update_status.assert_any_await(uuid.UUID(signal_id), OrderStatus.PARTIAL_EXPOSURE)
        # Must not persist requested Leg B size when the broker filled less.
        leg_b_fill_calls = [c for c in mock_update_fill.await_args_list if c.args[1] == "leg-b"]
        assert leg_b_fill_calls
        assert leg_b_fill_calls[0].kwargs["filled_quantity"] == pytest.approx(0.333333)
        mock_close_trade.assert_awaited()
        assert monitor.brokerage.place_value_order.await_count == 4


@pytest.mark.asyncio
async def test_execute_trade_blocks_when_pending_orders_budget_read_fails(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
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

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
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

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
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
        # Pre-submit row first; promote via attach_broker_order_id on ambiguous submit.
        assert mock_log_trade.await_args_list[0].args[0]["status"] == OrderStatus.ORDER_SUBMITTED
        assert mock_log_trade.await_args_list[0].args[0]["order_id"] == f"{signal_id}-A"
        from src.services.persistence_service import persistence_service as _ps
        assert _ps.attach_broker_order_id.await_count >= 1
        attach_kwargs = _ps.attach_broker_order_id.await_args.kwargs
        assert attach_kwargs["status"] == OrderStatus.NEEDS_MANUAL_RECONCILIATION
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

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
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

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.services.persistence_service.persistence_service.update_trade_fill", new_callable=AsyncMock, create=True) as mock_update_fill, \
         patch("src.services.persistence_service.persistence_service.close_trade", new_callable=AsyncMock) as mock_close_trade, \
         patch("src.services.notification_service.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 0.0):

        mock_bid_ask.return_value = (150.0, 150.1)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 300.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 300.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        mock_await_fill.side_effect = [
            {"status": "partially_filled", "filled_qty": 0.5, "filled_avg_price": 150.0},
            {"status": "filled", "filled_qty": 0.5, "filled_avg_price": 150.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "close-a"},
        ])

        result = await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert result["reason"] == "leg_a_unwound"
        assert monitor.brokerage.place_value_order.await_count == 2
        close_call = monitor.brokerage.place_value_order.await_args_list[1]
        assert close_call.args[0] == "AAPL"
        assert close_call.args[1] == pytest.approx(75.0)
        assert close_call.args[2] == "BUY"
        assert close_call.kwargs["client_order_id"] == f"{signal_id}-A-PARTIAL-CLOSE"
        mock_await_fill.assert_any_await("leg-a", timeout=30)
        mock_await_fill.assert_any_await("close-a", timeout=30)
        mock_sleep.assert_not_awaited()
        mock_log_journal.assert_not_awaited()
        mock_close_trade.assert_awaited_once()
        mock_update_status.assert_any_await(uuid.UUID(signal_id), OrderStatus.CLOSED)
        mock_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_trade_emergency_closes_leg_a_when_leg_b_fails(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.services.persistence_service.persistence_service.close_trade", new_callable=AsyncMock) as mock_close_trade, \
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
        mock_close_trade.assert_awaited_once()
        assert mock_close_trade.await_args.args[0] == uuid.UUID(signal_id)
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

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock) as mock_log_journal, \
         patch("src.services.persistence_service.persistence_service.update_signal_status", new_callable=AsyncMock) as mock_update_status, \
         patch("src.services.persistence_service.persistence_service.close_trade", new_callable=AsyncMock) as mock_close_trade, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 0.0):

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
        # Unwind the actual filled Leg A exposure ($150), not the plan notional.
        assert close_call.args[1] == pytest.approx(150.0)
        mock_await_fill.assert_any_await("leg-a", timeout=30)
        mock_await_fill.assert_any_await("leg-b", timeout=30)
        mock_await_fill.assert_any_await("close-a", timeout=30)
        mock_log_journal.assert_not_awaited()
        mock_update_status.assert_any_await(
            uuid.UUID(signal_id),
            OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
        )
        mock_close_trade.assert_awaited_once()
        assert mock_close_trade.await_args.args[0] == uuid.UUID(signal_id)
        mock_notify.assert_not_awaited()
        assert mock_log_trade.await_count == 2


@pytest.mark.asyncio
async def test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
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
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 0.0):

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

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
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
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 0.0):

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

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
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
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 0.0):

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
async def test_execute_trade_paper_logs_entry_journal_before_shadow(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())
    call_order = []

    async def log_journal(payload):
        call_order.append(("journal", payload))

    async def execute_shadow(*args, **kwargs):
        call_order.append(("shadow", {"args": args, "kwargs": kwargs}))

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new=AsyncMock(side_effect=log_journal)) as mock_log_journal, \
         patch("src.services.shadow_service.shadow_service.execute_simulated_trade", new=AsyncMock(side_effect=execute_shadow)) as mock_shadow_exec, \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(settings, "PAPER_TRADING", True), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 0.0):

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

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock) as mock_log_trade, \
         patch("src.services.persistence_service.persistence_service.update_trade_fill", new_callable=AsyncMock) as mock_update_fill, \
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
        # Match planned crypto sizes under $100 gross (ETH~$3.84 / BTC~$96.15).
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 0.001923, "filled_avg_price": 2000.0},
            {"status": "filled", "filled_qty": 0.001923, "filled_avg_price": 50000.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "crypto-leg-a"},
            {"status": "success", "order_id": "crypto-leg-b"},
        ])

        await monitor.execute_trade(pair, "Short-Long", 2000.0, 50000.0, signal_id)

        assert monitor.brokerage.place_value_order.await_count == 2
        monitor.brokerage.get_account_cash.assert_called_once()
        mock_shadow_exec.assert_not_called()
        assert mock_log_trade.await_count == 2
        assert mock_update_fill.await_count == 2
        mock_log_journal.assert_awaited_once()
        assert mock_await_fill.await_count == 2

@pytest.mark.asyncio
async def test_execute_trade_crypto_budget_cap_applied(monitor):
    pair = {"ticker_a": "ETH-USD", "ticker_b": "BTC-USD", "id": "ETH-USD_BTC-USD"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
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
            {"status": "filled", "filled_qty": 0.001923, "filled_avg_price": 2000.0},
            {"status": "filled", "filled_qty": 0.001923, "filled_avg_price": 50000.0},
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
async def test_execute_trade_accepts_filled_qty_under_plan(monitor):
    """Notional fills often deliver slightly less qty than the mid-price plan."""
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    signal_id = str(uuid.uuid4())

    async def bid_ask_for(ticker, *args, **kwargs):
        if "BTC" in str(ticker).upper():
            return (65000.0, 65001.0)
        return (3200.0, 3201.0)

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock, side_effect=bid_ask_for) as mock_bid_ask, \
         patch("src.services.persistence_service.persistence_service.log_trade", new_callable=AsyncMock), \
         patch("src.services.persistence_service.persistence_service.update_trade_fill", new_callable=AsyncMock), \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock), \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock) as mock_regime, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch("src.monitor.asyncio.sleep", new_callable=AsyncMock), \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 100.0):

        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 100.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 100.0,
        }
        mock_regime.return_value = {"regime": "Normal", "confidence": 0.9, "features": {}}
        # Planned ≈ 0.001467 BTC / 0.001467 ETH at $100 gross; ~2% under is accepted.
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 0.001438, "filled_avg_price": 65000.0},
            {"status": "filled", "filled_qty": 0.001438, "filled_avg_price": 3200.0},
        ]
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "leg-a"},
            {"status": "success", "order_id": "leg-b"},
        ])
        monitor.brokerage.get_positions = AsyncMock(return_value=[{
            "ticker": "ETH-USD",
            "symbol": "ETH-USD",
            "quantity": 1.0,
            "quantityAvailableForTrading": 1.0,
            "marketValue": 50_000.0,
        }])

        result = await monitor.execute_trade(pair, "Long-Short", 65000.0, 3200.0, signal_id)

        assert result["executed"] is True
        assert monitor.brokerage.place_value_order.await_count == 2
        assert mock_await_fill.await_count == 2
        assert mock_bid_ask.await_count >= 1


@pytest.mark.asyncio
async def test_execute_trade_rejects_crypto_sell_without_inventory(monitor):
    pair = {"ticker_a": "BTC-USD", "ticker_b": "ETH-USD", "id": "BTC-USD_ETH-USD"}
    signal_id = str(uuid.uuid4())

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock) as mock_bid_ask, \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 100.0):

        mock_bid_ask.return_value = (100.0, 100.05)
        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 100.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 100.0,
        }
        monitor.brokerage.get_positions = AsyncMock(return_value=[])
        monitor.brokerage.place_value_order = AsyncMock()

        result = await monitor.execute_trade(pair, "Short-Long", 65000.0, 3200.0, signal_id)

        assert result["executed"] is False
        assert result["reason"] == "insufficient_sell_inventory"
        monitor.brokerage.place_value_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_trade_rejects_sector_overconcentration(monitor):
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())
    # Relative to PAPER_TRADING_STARTING_CASH=1000, 400 tech + ~100 new => ~50% > 30%.
    crowded = [
        {"ticker": "GOOGL", "size": 200.0, "sector": "Technology"},
        {"ticker": "NVDA", "size": 200.0, "sector": "Technology"},
    ]

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock, return_value=(150.0, 150.1)), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=crowded), \
         patch("src.services.shadow_service.shadow_service.execute_simulated_trade", new_callable=AsyncMock) as mock_shadow_exec, \
         patch("src.services.persistence_service.persistence_service.get_open_signals", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock), \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock, return_value={"regime": "STABLE", "confidence": 0.9, "features": {}}), \
         patch.object(monitor, "_has_active_pair_or_pending_order", new_callable=AsyncMock, return_value=False), \
         patch.object(settings, "PAPER_TRADING", True), \
         patch.object(settings, "PAPER_TRADING_STARTING_CASH", 1000.0), \
         patch.object(settings, "ALPACA_BUDGET_USD", 0.0), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 100.0), \
         patch.object(settings, "MAX_SECTOR_EXPOSURE", 0.30):

        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 100.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 100.0,
            "fee_status": {"total_friction_percent": 0.001},
        }
        result = await monitor.execute_trade(pair, "Short-Long", 150.0, 300.0, signal_id)

        assert result["executed"] is False
        assert result["reason"] == "sector_exposure_guard"
        mock_shadow_exec.assert_not_called()


@pytest.mark.asyncio
async def test_execute_trade_rejects_shared_leg_overlap(monitor):
    pair = {"ticker_a": "NVDA", "ticker_b": "INTC", "id": "NVDA_INTC"}
    signal_id = str(uuid.uuid4())
    open_signals = [
        {
            "signal_id": "existing",
            "is_shadow": True,
            "execution_lane": "SHADOW",
            "legs": [{"ticker": "NVDA", "is_shadow": True}, {"ticker": "AMD", "is_shadow": True}],
            "total_cost_basis": 100.0,
        }
    ]

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock, return_value=(100.0, 100.05)), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.shadow_service.shadow_service.execute_simulated_trade", new_callable=AsyncMock) as mock_shadow_exec, \
         patch("src.services.persistence_service.persistence_service.get_open_signals", new_callable=AsyncMock, return_value=open_signals), \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock), \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock, return_value={"regime": "STABLE", "confidence": 0.9, "features": {}}), \
         patch.object(monitor, "_has_active_pair_or_pending_order", new_callable=AsyncMock, return_value=False), \
         patch.object(settings, "PAPER_TRADING", True), \
         patch.object(settings, "BLOCK_SHARED_LEG_OPENS", True), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 100.0):

        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 100.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 100.0,
            "fee_status": {"total_friction_percent": 0.001},
        }
        result = await monitor.execute_trade(pair, "Short-Long", 100.0, 50.0, signal_id)

        assert result["executed"] is False
        assert result["reason"] == "shared_leg_guard"
        mock_shadow_exec.assert_not_called()


@pytest.mark.asyncio
async def test_execute_trade_rejects_max_open_pairs(monitor):
    pair = {"ticker_a": "KO", "ticker_b": "PEP", "id": "KO_PEP"}
    signal_id = str(uuid.uuid4())
    open_signals = [
        {
            "signal_id": f"sig-{i}",
            "is_shadow": True,
            "execution_lane": "SHADOW",
            "legs": [{"ticker": f"T{i}A"}, {"ticker": f"T{i}B"}],
            "total_cost_basis": 50.0,
        }
        for i in range(8)
    ]

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock, return_value=(50.0, 50.05)), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.shadow_service.shadow_service.execute_simulated_trade", new_callable=AsyncMock) as mock_shadow_exec, \
         patch("src.services.persistence_service.persistence_service.get_open_signals", new_callable=AsyncMock, return_value=open_signals), \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock), \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock, return_value={"regime": "STABLE", "confidence": 0.9, "features": {}}), \
         patch.object(monitor, "_has_active_pair_or_pending_order", new_callable=AsyncMock, return_value=False), \
         patch.object(settings, "PAPER_TRADING", True), \
         patch.object(settings, "MAX_OPEN_PAIRS", 8), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 100.0):

        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 100.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 100.0,
            "fee_status": {"total_friction_percent": 0.001},
        }
        result = await monitor.execute_trade(pair, "Short-Long", 50.0, 50.0, signal_id)

        assert result["executed"] is False
        assert result["reason"] == "max_open_pairs_guard"
        mock_shadow_exec.assert_not_called()


@pytest.mark.asyncio
async def test_execute_trade_rejects_portfolio_gross_cap(monitor):
    pair = {"ticker_a": "KO", "ticker_b": "PEP", "id": "KO_PEP"}
    signal_id = str(uuid.uuid4())
    open_signals = [
        {
            "signal_id": "big",
            "is_shadow": True,
            "execution_lane": "SHADOW",
            "legs": [{"ticker": "XOM"}, {"ticker": "CVX"}],
            "total_cost_basis": 750.0,
        }
    ]

    with patch("src.monitor.data_service.get_bid_ask", new_callable=AsyncMock, return_value=(50.0, 50.05)), \
         patch("src.services.risk_service.risk_service.validate_trade") as mock_validate_trade, \
         patch("src.services.budget_service.budget_service.get_effective_cash", return_value=1000.0), \
         patch("src.services.budget_service.budget_service.get_venue_budget_info", return_value={"total": 1000.0, "used": 0.0, "remaining": 1000.0}), \
         patch("src.services.shadow_service.shadow_service.get_active_portfolio_with_sectors", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.shadow_service.shadow_service.execute_simulated_trade", new_callable=AsyncMock) as mock_shadow_exec, \
         patch("src.services.persistence_service.persistence_service.get_open_signals", new_callable=AsyncMock, return_value=open_signals), \
         patch("src.services.persistence_service.persistence_service.log_trade_journal", new_callable=AsyncMock), \
         patch("src.services.market_regime_service.market_regime_service.classify_current_regime", new_callable=AsyncMock, return_value={"regime": "STABLE", "confidence": 0.9, "features": {}}), \
         patch.object(monitor, "_has_active_pair_or_pending_order", new_callable=AsyncMock, return_value=False), \
         patch.object(settings, "PAPER_TRADING", True), \
         patch.object(settings, "BLOCK_SHARED_LEG_OPENS", False), \
         patch.object(settings, "MAX_OPEN_PAIRS", 20), \
         patch.object(settings, "MAX_PORTFOLIO_GROSS_NOTIONAL_USD", 800.0), \
         patch.object(settings, "MAX_PAIR_GROSS_NOTIONAL_USD", 100.0):

        mock_validate_trade.return_value = {
            "is_acceptable": True,
            "final_amount": 100.0,
            "kelly_fraction": 0.1,
            "max_allowed_fiat": 100.0,
            "fee_status": {"total_friction_percent": 0.001},
        }
        result = await monitor.execute_trade(pair, "Short-Long", 50.0, 50.0, signal_id)

        assert result["executed"] is False
        assert result["reason"] == "portfolio_gross_notional_guard"
        mock_shadow_exec.assert_not_called()
