import asyncio
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.monitor import ArbitrageMonitor
from src.services.persistence_service import OrderStatus, ExitReason

@pytest.fixture
def monitor():
    m = ArbitrageMonitor(mode="test")
    m.brokerage = AsyncMock()
    # Mock preflight check to always pass
    m._preflight_live_sell_inventory = AsyncMock(return_value=True)
    return m

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
async def test_duplicate_close_call(mock_notif, mock_settings, mock_persistence, monitor, signal):
    """Test that a sequential duplicate call is blocked."""
    mock_settings.PAPER_TRADING = False
    mock_settings.DEV_MODE = False
    
    # DB initially OPEN, then CLOSING, then CLOSED
    mock_persistence.get_signal_status.side_effect = [
        OrderStatus.OPEN,
        OrderStatus.CLOSED
    ]
    
    # First call
    await monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT)
    
    # Second call
    await monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT)
    
    # Brokerage should only have placed orders for the first call (2 orders)
    assert monitor.brokerage.place_value_order.call_count == 2
    mock_persistence.update_signal_status.assert_called_once_with(
        uuid.UUID(signal["signal_id"]), OrderStatus.CLOSING
    )

@pytest.mark.asyncio
@patch("src.monitor.persistence_service")
@patch("src.monitor.settings")
async def test_concurrent_duplicate_close(mock_settings, mock_persistence, monitor, signal):
    """Test that concurrent calls are blocked by the in-memory lock."""
    mock_settings.PAPER_TRADING = False
    mock_settings.DEV_MODE = False
    
    mock_persistence.get_signal_status.return_value = OrderStatus.OPEN
    
    # Add an artificial delay to the DB update so the lock does the work
    async def delayed_update(*args, **kwargs):
        await asyncio.sleep(0.1)
    
    mock_persistence.update_signal_status.side_effect = delayed_update
    
    # Gather two concurrent close calls
    await asyncio.gather(
        monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT),
        monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT)
    )
    
    # Only one should get past the lock and call the brokerage
    assert monitor.brokerage.place_value_order.call_count == 2
    mock_persistence.update_signal_status.assert_called_once()

@pytest.mark.asyncio
@patch("src.monitor.persistence_service")
@patch("src.monitor.settings")
@patch("src.monitor.notification_service")
async def test_first_leg_closes_second_leg_fails(mock_notif, mock_settings, mock_persistence, monitor, signal):
    """Test when brokerage returns an error on the second leg."""
    mock_settings.PAPER_TRADING = False
    mock_settings.DEV_MODE = False
    
    mock_persistence.get_signal_status.return_value = OrderStatus.OPEN
    
    # First place_value_order succeeds, second fails
    monitor.brokerage.place_value_order.side_effect = [
        {"status": "success"},
        {"status": "error", "message": "Insufficient shares"}
    ]
    
    # Since we added `return` on `res.get("status") == "error"`, it will return early.
    # Wait, the code says: `if res.get("status") == "error": msg = ...; logger.error(msg); await notification_service.send_message(msg); return`
    await monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT)
    
    # Should have called notification service
    mock_notif.send_message.assert_called_once()
    assert "Close aborted" in mock_notif.send_message.call_args[0][0]
    
    # It didn't reach close_trade
    mock_persistence.close_trade.assert_not_called()

@pytest.mark.asyncio
@patch("src.monitor.persistence_service")
@patch("src.monitor.settings")
@patch("src.monitor.notification_service")
async def test_close_function_raises_exception(mock_notif, mock_settings, mock_persistence, monitor, signal):
    """Test when the close path raises an unhandled exception."""
    mock_settings.PAPER_TRADING = False
    mock_settings.DEV_MODE = False
    
    mock_persistence.get_signal_status.return_value = OrderStatus.OPEN
    
    # Brokerage raises an exception
    monitor.brokerage.place_value_order.side_effect = Exception("API Down")
    
    with pytest.raises(Exception, match="API Down"):
        await monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT)
    
    # State should be updated to CLOSE_FAILED
    mock_persistence.update_signal_status.assert_any_call(uuid.UUID(signal["signal_id"]), OrderStatus.CLOSE_FAILED)
    
    # Critical alert sent
    mock_notif.send_message.assert_called_once()
    assert "CRITICAL — _close_position FAILED" in mock_notif.send_message.call_args[0][0]

@pytest.mark.asyncio
@patch("src.monitor.persistence_service")
@patch("src.monitor.settings")
@patch("src.monitor.notification_service")
async def test_kill_switch_close_failure(mock_notif, mock_settings, mock_persistence, monitor, signal):
    """Test kill-switch close raising an exception correctly alerts."""
    mock_settings.PAPER_TRADING = False
    mock_settings.DEV_MODE = False
    
    mock_persistence.get_signal_status.return_value = OrderStatus.OPEN
    
    # Force exception
    monitor.brokerage.place_value_order.side_effect = RuntimeError("Broker Error")
    
    with pytest.raises(RuntimeError):
        await monitor._close_position(signal, 155.0, 295.0, ExitReason.KILL_SWITCH)
    
    # State should be updated to CLOSE_FAILED
    mock_persistence.update_signal_status.assert_any_call(uuid.UUID(signal["signal_id"]), OrderStatus.CLOSE_FAILED)
    
    # Alert should mention KILL_SWITCH
    alert_msg = mock_notif.send_message.call_args[0][0]
    assert "KILL_SWITCH" in alert_msg
    assert "CRITICAL" in alert_msg

@pytest.mark.asyncio
@patch("src.monitor.persistence_service")
async def test_bot_restart_while_closing(mock_persistence, monitor, signal):
    """Test that if the DB state is CLOSING (from a previous crashed run), it doesn't duplicate but handles it."""
    # If the DB says CLOSING, the idempotency check allows it to resume
    mock_persistence.get_signal_status.return_value = OrderStatus.CLOSING
    
    # It should proceed to close
    monitor.brokerage.place_value_order.return_value = {"status": "success"}
    
    await monitor._close_position(signal, 155.0, 295.0, ExitReason.TAKE_PROFIT)
    
    # Orders should have been placed
    assert monitor.brokerage.place_value_order.call_count == 2
    mock_persistence.update_signal_status.assert_called_with(uuid.UUID(signal["signal_id"]), OrderStatus.CLOSING)
