import pytest
import asyncio
from datetime import datetime, timedelta
from src.services.dca_service import dca_service
from src.agents.portfolio_manager_agent import portfolio_manager
from src.models.persistence import PersistenceManager
from src.config import settings
from unittest.mock import patch, MagicMock

def test_portfolio_allocation_flow():
    persistence = PersistenceManager(settings.DB_PATH)
    
    # 1. Define strategy
    strategy_id = "test_strat"
    persistence.save_portfolio_strategy(strategy_id, "AAPL", 0.6, "Balanced")
    persistence.save_portfolio_strategy(strategy_id, "MSFT", 0.4, "Balanced")
    
    # 2. Mock brokerage to avoid real orders
    with patch('src.services.brokerage_service.BrokerageService.place_value_order') as mock_order:
        mock_order.return_value = {"status": "success"}
        
        # 3. Trigger allocation
        asyncio.run(portfolio_manager.allocate_funds(strategy_id, 100.0))
        
        # 4. Verify orders
        assert mock_order.call_count == 2
        calls = [c.args for c in mock_order.call_args_list]
        
        # Check AAPL call
        aapl_call = next(c for c in calls if c[0] == "AAPL")
        assert aapl_call[1] == 60.0
        
        # Check MSFT call
        msft_call = next(c for c in calls if c[0] == "MSFT")
        assert msft_call[1] == 40.0

def test_dca_reinvest_logic():
    # Verify DRIP logic
    persistence = PersistenceManager(settings.DB_PATH)
    persistence.set_fee_config('drip_enabled', 1.0)
    persistence.set_fee_config('min_trade_value', 5.0)
    
    # Define 'safe' strategy for DRIP
    persistence.save_portfolio_strategy("safe", "SPY", 1.0, "Conservative")
    
    with patch('src.services.brokerage_service.BrokerageService.get_account_cash') as mock_cash:
        mock_cash.return_value = 10.0 # Above $5 threshold
        
        with patch.object(dca_service, 'execute_dca') as mock_exec:
            asyncio.run(dca_service.sweep_dividends())
            
            mock_exec.assert_called_once()
            args = mock_exec.call_args.args[0]
            assert args['strategy_id'] == 'safe'
            assert args['amount'] == 10.0
