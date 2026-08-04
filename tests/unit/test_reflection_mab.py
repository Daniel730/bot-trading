import pytest
import sys
import os
import uuid

# Ensure src is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from unittest.mock import patch, MagicMock, AsyncMock
from src.agents.reflection_agent import ReflectionAgent, reflection_agent
from src.services.persistence_service import OrderSide


def _mock_session_factory(trades, journal=None):
    mock_scalar_result = MagicMock()
    mock_scalar_result.all.return_value = trades
    mock_ledger_result = MagicMock()
    mock_ledger_result.scalars.return_value = mock_scalar_result
    mock_journal_result = MagicMock()
    mock_journal_result.scalar_one_or_none.return_value = journal

    mock_session_context = MagicMock()
    mock_session_context.execute = AsyncMock(
        side_effect=[mock_ledger_result, mock_journal_result]
    )
    return mock_session_context


@pytest.mark.asyncio
async def test_reflection_reward_logic_success():
    """Verify that a successful BUY signal rewards Bull and SEC from real PnL."""
    signal_id = str(uuid.uuid4())

    mock_trade = MagicMock()
    mock_trade.side = OrderSide.BUY
    mock_trade.metadata_json = {"pnl": 50.0}

    with patch('src.services.persistence_service.persistence_service.update_agent_metrics', new_callable=AsyncMock) as mock_update, \
         patch('src.services.persistence_service.persistence_service.AsyncSessionLocal') as mock_session_factory, \
         patch('src.agents.reflection_agent.asyncio.sleep', new_callable=AsyncMock):

        mock_session_factory.return_value.__aenter__.return_value = _mock_session_factory([mock_trade])

        await reflection_agent.reflect_on_trade(signal_id)

        assert mock_update.call_count == 3
        mock_update.assert_any_call("BULL_AGENT", True)
        mock_update.assert_any_call("BEAR_AGENT", False)
        mock_update.assert_any_call("SEC_AGENT", True)


@pytest.mark.asyncio
async def test_reflection_reward_logic_failure():
    """Verify that a failed SELL signal penalizes Bull/SEC and rewards Bear."""
    signal_id = str(uuid.uuid4())

    mock_trade = MagicMock()
    mock_trade.side = OrderSide.SELL
    mock_trade.metadata_json = {"pnl": -20.0}

    with patch('src.services.persistence_service.persistence_service.update_agent_metrics', new_callable=AsyncMock) as mock_update, \
         patch('src.services.persistence_service.persistence_service.AsyncSessionLocal') as mock_session_factory, \
         patch('src.agents.reflection_agent.asyncio.sleep', new_callable=AsyncMock):

        mock_session_factory.return_value.__aenter__.return_value = _mock_session_factory([mock_trade])

        await reflection_agent.reflect_on_trade(signal_id)

        mock_update.assert_any_call("BULL_AGENT", False)
        mock_update.assert_any_call("BEAR_AGENT", True)
        mock_update.assert_any_call("SEC_AGENT", False)


@pytest.mark.asyncio
async def test_reflection_uses_signal_level_pnl_not_leg_sum():
    """close_trade stamps the same PnL on every leg — do not double-count."""
    signal_id = str(uuid.uuid4())

    # Two legs each stamped with the full signal PnL (as close_trade does).
    leg_a = MagicMock()
    leg_a.metadata_json = {"pnl": 50.0, "exit_reason": "TAKE_PROFIT"}
    leg_b = MagicMock()
    leg_b.metadata_json = {"pnl": 50.0, "exit_reason": "TAKE_PROFIT"}

    assert ReflectionAgent._signal_realized_pnl([leg_a, leg_b]) == 50.0

    with patch('src.services.persistence_service.persistence_service.update_agent_metrics', new_callable=AsyncMock) as mock_update, \
         patch('src.services.persistence_service.persistence_service.AsyncSessionLocal') as mock_session_factory, \
         patch('src.agents.reflection_agent.asyncio.sleep', new_callable=AsyncMock):

        mock_session_factory.return_value.__aenter__.return_value = _mock_session_factory([leg_a, leg_b])
        await reflection_agent.reflect_on_trade(signal_id)

        mock_update.assert_any_call("BULL_AGENT", True)
        mock_update.assert_any_call("BEAR_AGENT", False)
        mock_update.assert_any_call("SEC_AGENT", True)


@pytest.mark.asyncio
async def test_reflection_skips_mab_when_pnl_missing():
    """Missing realized PnL must not invent a failure reward for MAB arms."""
    signal_id = str(uuid.uuid4())

    mock_trade = MagicMock()
    mock_trade.metadata_json = {"exit_prices": {"AAPL": 100.0}}

    with patch('src.services.persistence_service.persistence_service.update_agent_metrics', new_callable=AsyncMock) as mock_update, \
         patch('src.services.persistence_service.persistence_service.AsyncSessionLocal') as mock_session_factory, \
         patch('src.agents.reflection_agent.asyncio.sleep', new_callable=AsyncMock), \
         patch('src.agents.reflection_agent.ReflectionAgent._update_global_agent_performance', new_callable=AsyncMock) as mock_ema:

        mock_session_factory.return_value.__aenter__.return_value = _mock_session_factory([mock_trade])
        await reflection_agent.reflect_on_trade(signal_id)

        mock_update.assert_not_called()
        mock_ema.assert_not_called()


@pytest.mark.asyncio
async def test_global_strategy_accuracy_ema_increments_sample_counter():
    """Self-esteem EMA updates accuracy and the measured-sample counter."""
    agent = ReflectionAgent()

    with patch(
        'src.services.persistence_service.persistence_service.get_system_state',
        new_callable=AsyncMock,
        side_effect=["0.5000", "2"],
    ) as mock_get, patch(
        'src.services.persistence_service.persistence_service.set_system_state',
        new_callable=AsyncMock,
    ) as mock_set:
        await agent._update_global_agent_performance(True)

        # EMA: 0.1 * 1.0 + 0.9 * 0.5 = 0.55
        mock_set.assert_any_call("global_strategy_accuracy", "0.5500")
        mock_set.assert_any_call("global_strategy_accuracy_samples", "3")
        assert mock_get.await_count == 2
