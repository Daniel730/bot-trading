import pytest
from unittest.mock import AsyncMock, patch
import uuid

from src.config import settings
from src.services.persistence_service import ExitReason, OrderStatus
from src.services.execution_lane import LANE_LIVE


@pytest.mark.asyncio
async def test_close_position_success(monitor):
    """
    S-07: Test _close_position path.
    """
    signal = {
        "execution_lane": LANE_LIVE,
        "is_shadow": False,
        "paper_trade": False,
        "signal_id": str(uuid.uuid4()),
        "legs": [
            {"ticker": "AAPL", "quantity": 10, "side": "BUY", "price": 150.0, "order_id": "leg-a"},
            {"ticker": "MSFT", "quantity": 5, "side": "SELL", "price": 300.0, "order_id": "leg-b"},
        ]
    }

    with patch("src.monitor.persistence_service") as mock_persistence, \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "DEV_MODE", False):
        mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
        mock_persistence.close_trade = AsyncMock()
        mock_persistence.update_signal_status = AsyncMock()
        mock_persistence.update_trade_fill = AsyncMock()
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "close-a"},
            {"status": "success", "order_id": "close-b"},
        ])
        monitor.brokerage.get_available_quantity.side_effect = [10.0, 0.0, 0.0]
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 10.0, "filled_avg_price": 160.0},
            {"status": "filled", "filled_qty": 5.0, "filled_avg_price": 290.0},
        ]

        await monitor._close_position(signal, 160.0, 290.0, ExitReason.TAKE_PROFIT)

        assert monitor.brokerage.place_value_order.await_count == 2
        assert mock_await_fill.await_count == 2
        mock_persistence.close_trade.assert_awaited_once()
        assert mock_persistence.update_trade_fill.await_count == 2
        for call in mock_persistence.update_trade_fill.await_args_list:
            assert call.kwargs["metadata_updates"]["remaining_qty"] == 0.0
            assert call.kwargs["metadata_updates"]["close_remaining_qty"] == 0.0


@pytest.mark.asyncio
async def test_close_position_does_not_close_ledger_until_all_close_orders_fill(monitor):
    signal_id = str(uuid.uuid4())
    signal = {
        "execution_lane": LANE_LIVE,
        "is_shadow": False,
        "paper_trade": False,
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
        "execution_lane": LANE_LIVE,
        "is_shadow": False,
        "paper_trade": False,
        "signal_id": signal_id,
        "legs": [
            {
                "ticker": "AAPL",
                "quantity": 10,
                "side": "BUY",
                "price": 150.0,
                "order_id": "leg-a",
                "filled_qty": 10.0,
            },
            {
                "ticker": "MSFT",
                "quantity": 5,
                "side": "SELL",
                "price": 300.0,
                "order_id": "leg-b",
                "filled_qty": 5.0,
            },
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
        mock_persistence.update_trade_fill = AsyncMock()
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
        assert mock_persistence.update_trade_fill.await_count >= 2
        shortfall_call = mock_persistence.update_trade_fill.await_args_list[-1]
        assert shortfall_call.args[1] == "leg-b"
        assert shortfall_call.kwargs["status"] == OrderStatus.NEEDS_MANUAL_RECONCILIATION
        assert shortfall_call.kwargs["metadata_updates"]["close_filled_qty"] == pytest.approx(2.5)
        assert shortfall_call.kwargs["metadata_updates"]["close_remaining_qty"] == pytest.approx(2.5)
        assert shortfall_call.kwargs["metadata_updates"]["remaining_qty"] == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_close_position_does_not_close_ledger_when_broker_reports_residual_position(monitor):
    signal_id = str(uuid.uuid4())
    signal = {
        "execution_lane": LANE_LIVE,
        "is_shadow": False,
        "paper_trade": False,
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
         patch.object(settings, "IGNORE_UNMANAGED_POSITIONS", False), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill:

        mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
        mock_persistence.close_trade = AsyncMock()
        mock_persistence.update_signal_status = AsyncMock()
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "close-a"},
            {"status": "success", "order_id": "close-b"},
        ])
        monitor.brokerage.get_available_quantity.side_effect = [10.0, 0.25]
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 10.0, "filled_avg_price": 160.0},
            {"status": "filled", "filled_qty": 5.0, "filled_avg_price": 290.0},
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
        assert "broker still reports 0.250000 remaining AAPL" in mock_notify.await_args.args[0]


@pytest.mark.asyncio
async def test_close_position_closes_ledger_when_residual_ignored(monitor):
    signal_id = str(uuid.uuid4())
    signal = {
        "execution_lane": LANE_LIVE,
        "is_shadow": False,
        "paper_trade": False,
        "signal_id": signal_id,
        "legs": [
            {"ticker": "BTC-USD", "quantity": 0.000732, "side": "BUY", "price": 65000.0},
            {"ticker": "ETH-USD", "quantity": 0.026762, "side": "SELL", "price": 1900.0},
        ],
        "total_cost_basis": 100.0,
    }

    with patch("src.monitor.persistence_service") as mock_persistence, \
         patch("src.monitor.notification_service.send_message", new_callable=AsyncMock) as mock_notify, \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "DEV_MODE", False), \
         patch.object(settings, "IGNORE_UNMANAGED_POSITIONS", True), \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill:

        mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
        mock_persistence.close_trade = AsyncMock()
        mock_persistence.update_signal_status = AsyncMock()
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {"status": "success", "order_id": "close-btc"},
            {"status": "success", "order_id": "close-eth"},
        ])
        # Unmanaged residual inventory remains after managed close fills.
        monitor.brokerage.get_available_quantity.side_effect = [0.17, 0.06]
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 0.000732, "filled_avg_price": 65000.0},
            {"status": "filled", "filled_qty": 0.026216601, "filled_avg_price": 1900.0},
        ]

        await monitor._close_position(signal, 65000.0, 1900.0, ExitReason.TAKE_PROFIT)

        mock_persistence.close_trade.assert_awaited_once()
        mock_persistence.update_signal_status.assert_not_awaited()
        # Residual unmanaged inventory must alert — never silently swallow risk.
        assert mock_notify.await_count >= 1
        residual_alerts = [
            call.args[0] for call in mock_notify.await_args_list if "remaining" in call.args[0]
        ]
        assert residual_alerts
        assert "NOT auto-flattened" in residual_alerts[0]
        assert "IGNORE_UNMANAGED_POSITIONS=True" in residual_alerts[0]


@pytest.mark.asyncio
async def test_close_position_retries_with_new_client_order_id_on_terminal_duplicate(monitor):
    signal_id = str(uuid.uuid4())
    signal = {
        "execution_lane": LANE_LIVE,
        "is_shadow": False,
        "paper_trade": False,
        "signal_id": signal_id,
        "legs": [
            {"ticker": "AAPL", "quantity": 10, "side": "BUY", "price": 150.0},
            {"ticker": "MSFT", "quantity": 5, "side": "SELL", "price": 300.0},
        ],
    }

    with patch("src.monitor.persistence_service") as mock_persistence, \
         patch.object(monitor, "_await_order_fill", new_callable=AsyncMock) as mock_await_fill, \
         patch.object(settings, "PAPER_TRADING", False), \
         patch.object(settings, "DEV_MODE", False):
        mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
        mock_persistence.close_trade = AsyncMock()
        mock_persistence.update_signal_status = AsyncMock()
        monitor.brokerage.place_value_order = AsyncMock(side_effect=[
            {
                "status": "error",
                "terminal_duplicate": True,
                "prior_order_status": "rejected",
                "client_order_id": f"{signal_id}-CLOSE-AAPL",
                "message": "bound to terminal order",
            },
            {"status": "success", "order_id": "close-a-retry"},
            {"status": "success", "order_id": "close-b"},
        ])
        # Preflight inventory check, then post-close residual checks.
        monitor.brokerage.get_available_quantity.side_effect = [10.0, 0.0, 0.0]
        mock_await_fill.side_effect = [
            {"status": "filled", "filled_qty": 10.0, "filled_avg_price": 160.0},
            {"status": "filled", "filled_qty": 5.0, "filled_avg_price": 290.0},
        ]

        await monitor._close_position(signal, 160.0, 290.0, ExitReason.TAKE_PROFIT)

        assert monitor.brokerage.place_value_order.await_count == 3
        first = monitor.brokerage.place_value_order.await_args_list[0]
        retry = monitor.brokerage.place_value_order.await_args_list[1]
        assert first.kwargs["client_order_id"] == f"{signal_id}-CLOSE-AAPL"
        assert retry.kwargs["client_order_id"].startswith(f"{signal_id}-CLOSE-AAPL-R")
        mock_persistence.close_trade.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_position_skips_sell_when_broker_has_no_shares(monitor):
    signal = {
        "execution_lane": LANE_LIVE,
        "is_shadow": False,
        "paper_trade": False,
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
