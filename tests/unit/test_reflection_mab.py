import pytest
import sys
import os
import uuid
from datetime import datetime

# Ensure src is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from unittest.mock import patch, MagicMock, AsyncMock
from src.agents.reflection_agent import reflection_agent
from src.services.persistence_service import OrderSide, OrderStatus

@pytest.mark.asyncio
async def test_reflection_reward_logic_success():
    """
    Test F2: Verify that a successful BUY signal rewards Bull and SEC.
    """
    signal_id = str(uuid.uuid4())
    
    mock_trade = MagicMock()
    mock_trade.side = OrderSide.BUY
    mock_trade.metadata_json = {"pnl": 50.0}
    
    # We patch the persistence_service directly
    with patch('src.services.persistence_service.persistence_service.update_agent_metrics', new_callable=AsyncMock) as mock_update, \
         patch('src.services.persistence_service.persistence_service.AsyncSessionLocal') as mock_session_factory:
        
        # mock_session_factory() returns mock_session
        # mock_session.__aenter__() returns session_context
        # session_context.execute() returns result
        # result.all() returns trades
        
        mock_scalar_result = MagicMock()
        mock_scalar_result.all.return_value = [mock_trade]
        mock_ledger_result = MagicMock()
        mock_ledger_result.scalars.return_value = mock_scalar_result
        mock_journal_result = MagicMock()
        mock_journal_result.scalar_one_or_none.return_value = None

        mock_session_context = MagicMock()
        mock_session_context.execute = AsyncMock(
            side_effect=[mock_ledger_result, mock_journal_result]
        )
        
        mock_session_factory.return_value.__aenter__.return_value = mock_session_context
        
        await reflection_agent.reflect_on_trade(signal_id)
        
        assert mock_update.call_count == 3
        mock_update.assert_any_call("BULL_AGENT", True)
        mock_update.assert_any_call("BEAR_AGENT", False)
        mock_update.assert_any_call("SEC_AGENT", True)

@pytest.mark.asyncio
async def test_reflection_reward_logic_failure():
    """
    Test F2: Verify that a failed SELL signal rewards Bull and penalizes Bear/SEC.
    """
    signal_id = str(uuid.uuid4())
    
    mock_trade = MagicMock()
    mock_trade.side = OrderSide.SELL
    mock_trade.metadata_json = {"pnl": -20.0}
    
    with patch('src.services.persistence_service.persistence_service.update_agent_metrics', new_callable=AsyncMock) as mock_update, \
         patch('src.services.persistence_service.persistence_service.AsyncSessionLocal') as mock_session_factory:
        
        mock_scalar_result = MagicMock()
        mock_scalar_result.all.return_value = [mock_trade]
        mock_ledger_result = MagicMock()
        mock_ledger_result.scalars.return_value = mock_scalar_result
        mock_journal_result = MagicMock()
        mock_journal_result.scalar_one_or_none.return_value = None

        mock_session_context = MagicMock()
        mock_session_context.execute = AsyncMock(
            side_effect=[mock_ledger_result, mock_journal_result]
        )
        
        mock_session_factory.return_value.__aenter__.return_value = mock_session_context
        
        await reflection_agent.reflect_on_trade(signal_id)
        
        mock_update.assert_any_call("BULL_AGENT", False)
        mock_update.assert_any_call("BEAR_AGENT", True)
        mock_update.assert_any_call("SEC_AGENT", False)
