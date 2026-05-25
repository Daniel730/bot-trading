import pytest
from unittest.mock import AsyncMock, patch
import uuid

from src.config import settings
from src.services.persistence_service import ExitReason, OrderStatus


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
