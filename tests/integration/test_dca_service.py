import pytest
import asyncio
from datetime import datetime, timedelta
from src.services.dca_service import DCAService
from src.models.persistence import PersistenceManager

@pytest.mark.asyncio
async def test_dca_scheduling_and_execution():
    db = PersistenceManager(":memory:") # Use in-memory for testing
    dca_service = DCAService(db)
    
    # Setup a strategy and DCA schedule
    strategy_id = "test_strat"
    db.save_portfolio_strategy(strategy_id, "AAPL", 1.0, "Balanced")
    
    # Schedule for 1 second in the past to trigger immediately
    next_run = datetime.now() - timedelta(seconds=1)
    schedule_id = db.save_dca_schedule(amount=10.0, frequency="Daily", strategy_id=strategy_id, next_run=next_run)
    
    # Run service loop once
    executed_count = await dca_service.process_pending_dca()
    
    assert executed_count == 1
    
    # Verify next_run was updated
    schedules = db.get_active_dca_schedules()
    assert datetime.fromisoformat(schedules[0]["next_run"]) > datetime.now()
