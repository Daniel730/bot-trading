import asyncio
import uuid
import pytest
from unittest.mock import AsyncMock, patch

from src.services.persistence_service import OrderStatus, ExitReason

@pytest.fixture
def close_workflow_monitor(monitor):
    monitor.mode = "test"
    monitor.brokerage = AsyncMock()
    monitor.brokerage.place_value_order = AsyncMock(return_value={"status": "success", "order_id": "close-order"})
    monitor.brokerage.get_available_quantity = AsyncMock(return_value=0.0)
    # Mock preflight check to always pass
    monitor._preflight_live_sell_inventory = AsyncMock(return_value=True)
    monitor._await_order_fill = AsyncMock(return_value={"status": "filled", "filled_qty": 999})
    return monitor

@pytest.fixture
def signal():
    return {
        "signal_id": str(uuid.uuid4()),
        "legs": [
            {"ticker": "AAPL", "side": "BUY", "quantity": 10, "price": 150.0},
            {"ticker": "MSFT", "side": "SELL", "quantity": 5, "price": 300.0}
        ],
        "total_cost_basis": 1500.0
    }

@pytest.mark.asyncio
@patch("src.monitor.persistence_service")
@patch("src.monitor.settings")
@patch("src.monitor.notification_service")
async def test_duplicate_close_call(mock_notif, mock_settings, mock_persistence, close_workflow_monitor, signal):
    """Test that a sequential duplicate call is blocked."""
    mock_settings.PAPER_TRADING = False
    mock_settings.DEV_MODE = False
    mock_notif.send_message = AsyncMock()
    
    mock_persistence.mark_signal_closing_if_open = AsyncMock(side_effect=[True, False])
    mock_persistence.get_signal_status = AsyncMock(return_value=OrderStatus.CLOSED)
    mock_persistence.close_trade = AsyncMock()
    mock_persistence.update_signal_status = AsyncMock()

    async def slow_close_order(*args, **kwargs):
        await asyncio.sleep(0.01)
        return {"status": "success", "order_id": "close-order"}

    close_workflow_monitor.brokerage.place_value_order = AsyncMock(side_effect=slow_close_order)
    
    # First call
    await close_workflow_monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT)
    
    # Second call
    await close_workflow_monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT)
    
    # Brokerage should only have placed orders for the first call (2 orders)
    assert close_workflow_monitor.brokerage.place_value_order.call_count == 2
    assert mock_persistence.mark_signal_closing_if_open.call_count == 2

@pytest.mark.asyncio
@patch("src.monitor.persistence_service")
@patch("src.monitor.settings")
async def test_concurrent_duplicate_close(mock_settings, mock_persistence, close_workflow_monitor, signal):
    """Test that concurrent calls are blocked by the in-memory lock."""
    mock_settings.PAPER_TRADING = False
    mock_settings.DEV_MODE = False
    
    mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
    mock_persistence.get_signal_status = AsyncMock(return_value=OrderStatus.OPEN)
    mock_persistence.close_trade = AsyncMock()
    mock_persistence.update_signal_status = AsyncMock()

    async def slow_close_order(*args, **kwargs):
        await asyncio.sleep(0.01)
        return {"status": "success", "order_id": "close-order"}

    close_workflow_monitor.brokerage.place_value_order = AsyncMock(side_effect=slow_close_order)
    
    # Gather two concurrent close calls
    await asyncio.gather(
        close_workflow_monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT),
        close_workflow_monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT)
    )
    
    # Only one should get past the lock and call the brokerage
    assert close_workflow_monitor.brokerage.place_value_order.call_count == 2
    assert mock_persistence.mark_signal_closing_if_open.call_count == 1

@pytest.mark.asyncio
@patch("src.monitor.persistence_service")
@patch("src.monitor.settings")
@patch("src.monitor.notification_service")
async def test_first_leg_closes_second_leg_fails(mock_notif, mock_settings, mock_persistence, close_workflow_monitor, signal):
    """Test when brokerage returns an error on the second leg."""
    mock_settings.PAPER_TRADING = False
    mock_settings.DEV_MODE = False
    mock_notif.send_message = AsyncMock()
    
    mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
    mock_persistence.get_signal_status = AsyncMock(return_value=OrderStatus.OPEN)
    mock_persistence.close_trade = AsyncMock()
    mock_persistence.update_signal_status = AsyncMock()
    
    # First place_value_order succeeds, second fails
    close_workflow_monitor.brokerage.place_value_order.side_effect = [
        {"status": "success"},
        {"status": "error", "message": "Insufficient shares"}
    ]
    
    # Since we added `return` on `res.get("status") == "error"`, it will return early.
    # Wait, the code says: `if res.get("status") == "error": msg = ...; logger.error(msg); await notification_service.send_message(msg); return`
    await close_workflow_monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT)
    
    # Should have called notification service
    mock_notif.send_message.assert_called_once()
    assert "Close aborted" in mock_notif.send_message.call_args[0][0]
    
    # It didn't reach close_trade
    mock_persistence.close_trade.assert_not_called()

@pytest.mark.asyncio
@patch("src.monitor.persistence_service")
@patch("src.monitor.settings")
@patch("src.monitor.notification_service")
async def test_close_function_raises_exception(mock_notif, mock_settings, mock_persistence, close_workflow_monitor, signal):
    """Test when the close path raises an unhandled exception."""
    mock_settings.PAPER_TRADING = False
    mock_settings.DEV_MODE = False
    mock_notif.send_message = AsyncMock()
    
    mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
    mock_persistence.get_signal_status = AsyncMock(return_value=OrderStatus.OPEN)
    mock_persistence.close_trade = AsyncMock()
    mock_persistence.update_signal_status = AsyncMock()
    
    # Brokerage raises an exception
    close_workflow_monitor.brokerage.place_value_order.side_effect = Exception("API Down")
    
    with pytest.raises(Exception, match="API Down"):
        await close_workflow_monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT)
    
    # State should be updated to CLOSE_FAILED
    mock_persistence.update_signal_status.assert_any_call(uuid.UUID(signal["signal_id"]), OrderStatus.CLOSE_FAILED)
    
    # Critical alert sent
    mock_notif.send_message.assert_called_once()
    assert "CRITICAL — _close_position FAILED" in mock_notif.send_message.call_args[0][0]

@pytest.mark.asyncio
@patch("src.monitor.persistence_service")
@patch("src.monitor.settings")
@patch("src.monitor.notification_service")
async def test_kill_switch_close_failure(mock_notif, mock_settings, mock_persistence, close_workflow_monitor, signal):
    """Test kill-switch close raising an exception correctly alerts."""
    mock_settings.PAPER_TRADING = False
    mock_settings.DEV_MODE = False
    mock_notif.send_message = AsyncMock()
    
    mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=True)
    mock_persistence.get_signal_status = AsyncMock(return_value=OrderStatus.OPEN)
    mock_persistence.close_trade = AsyncMock()
    mock_persistence.update_signal_status = AsyncMock()
    
    # Force exception
    close_workflow_monitor.brokerage.place_value_order.side_effect = RuntimeError("Broker Error")
    
    with pytest.raises(RuntimeError):
        await close_workflow_monitor._close_position(signal, 155.0, 295.0, ExitReason.KILL_SWITCH)
    
    # State should be updated to CLOSE_FAILED
    mock_persistence.update_signal_status.assert_any_call(uuid.UUID(signal["signal_id"]), OrderStatus.CLOSE_FAILED)
    
    # Alert should mention KILL_SWITCH
    alert_msg = mock_notif.send_message.call_args[0][0]
    assert "KILL_SWITCH" in alert_msg
    assert "CRITICAL" in alert_msg

@pytest.mark.asyncio
@patch("src.monitor.persistence_service")
async def test_bot_restart_while_closing_is_blocked(mock_persistence, close_workflow_monitor, signal):
    """CLOSING rows are treated as already in-flight and are never re-closed by this worker."""
    mock_persistence.mark_signal_closing_if_open = AsyncMock(return_value=False)
    mock_persistence.get_signal_status = AsyncMock(return_value=OrderStatus.CLOSING)
    mock_persistence.update_signal_status = AsyncMock()

    await close_workflow_monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT)

    assert close_workflow_monitor.brokerage.place_value_order.call_count == 0
