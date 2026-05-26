import pytest
import uuid
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_spread_guard_rejection(monitor):
    """
    Test F3: Verify that the bot rejects a trade when the combined Bid-Ask spread
    exceeds the 0.3% threshold.
    """
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT"}
    signal_id = str(uuid.uuid4())

    # Mock high spread:
    # Leg A: 0.2% (Ask 100.2, Bid 100.0)
    # Leg B: 0.2% (Ask 50.1, Bid 50.0)
    # Total = 0.4% > 0.3%
    with patch.object(monitor, '_has_active_pair_or_pending_order', new_callable=AsyncMock, return_value=False), \
         patch('src.monitor.data_service.get_bid_ask', new_callable=AsyncMock, side_effect=[(100.0, 100.2), (50.0, 50.1)]), \
         patch('src.monitor.notification_service.send_message', new_callable=AsyncMock), \
         patch('src.monitor.logger') as mock_logger, \
         patch.object(monitor.brokerage, 'get_account_cash', return_value=2000.0):

        result = await monitor.execute_trade(pair, "BUY", 100.2, 50.0, signal_id)

        # Check that rejection log was called
        rej_log = [call for call in mock_logger.warning.call_args_list if "SPREAD GUARD: Rejecting" in call[0][0]]
        assert len(rej_log) == 1, "Monitor should have rejected the trade due to high spread."
        assert result["reason"] == "spread_guard"
        assert result["bid_a"] == 100.0
        assert result["ask_a"] == 100.2
        assert result["bid_b"] == 50.0
        assert result["ask_b"] == 50.1
        assert result["total_spread_pct"] == pytest.approx(0.4004)
        assert result["max_spread_pct"] == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_spread_guard_rejects_missing_bid_ask(monitor):
    """
    Missing or zero bid/ask data must fail closed before risk checks or orders.
    """
    monitor.brokerage.place_value_order = AsyncMock()

    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT", "id": "AAPL_MSFT"}
    signal_id = str(uuid.uuid4())

    with patch.object(monitor, '_has_active_pair_or_pending_order', new_callable=AsyncMock, return_value=False), \
         patch('src.monitor.data_service.get_bid_ask', new_callable=AsyncMock, side_effect=[(0.0, 0.0), (50.0, 50.1)]), \
         patch('src.monitor.risk_service.validate_trade', return_value={"is_acceptable": False, "rejection_reason": "test_stop"}) as mock_validate_trade, \
         patch('src.monitor.notification_service.send_message', new_callable=AsyncMock), \
         patch('src.monitor.logger') as mock_logger:

        await monitor.execute_trade(pair, "BUY", 100.0, 50.0, signal_id)

        mock_validate_trade.assert_not_called()
        monitor.brokerage.place_value_order.assert_not_called()
        rej_log = [
            call for call in mock_logger.warning.call_args_list
            if "SPREAD GUARD: Missing or invalid Bid/Ask" in call[0][0]
        ]
        assert len(rej_log) == 1, "Monitor should have rejected the trade due to missing bid/ask."


@pytest.mark.asyncio
async def test_spread_guard_acceptance(monitor):
    """
    Test F3: Verify that the bot proceeds when the spread is within limits.
    """
    pair = {"ticker_a": "AAPL", "ticker_b": "MSFT"}
    signal_id = str(uuid.uuid4())

    # Mock low spread: Total 0.1% < 0.3%
    with patch.object(monitor, '_has_active_pair_or_pending_order', new_callable=AsyncMock, return_value=False), \
         patch('src.monitor.data_service.get_bid_ask', new_callable=AsyncMock, side_effect=[(100.0, 100.05), (50.0, 50.02)]), \
         patch('src.monitor.logger') as mock_logger, \
         patch('src.monitor.risk_service.validate_trade', return_value={"is_acceptable": False, "status": "REJECT", "rejection_reason": "test_stop"}) as mock_validate_trade, \
         patch('src.monitor.notification_service.send_message', new_callable=AsyncMock), \
         patch.object(monitor.brokerage, 'get_account_cash', return_value=2000.0), \
         patch.object(monitor.brokerage, 'get_account_equity', return_value=2000.0), \
         patch.object(monitor.brokerage, 'get_account_buying_power', return_value=2000.0), \
         patch.object(monitor.brokerage, 'get_pending_orders_value', return_value=0.0):

        await monitor.execute_trade(pair, "BUY", 100.05, 50.0, signal_id)

        # Check that rejection log was NOT called
        rej_log = [call for call in mock_logger.warning.call_args_list if "SPREAD GUARD: Rejecting" in call[0][0]]
        assert len(rej_log) == 0, "Monitor should NOT have rejected the trade for spread."

        # Verify it proceeded to risk validation
        assert mock_validate_trade.called
