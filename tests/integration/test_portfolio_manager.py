import pytest
from datetime import datetime, timedelta
from src.agents.portfolio_manager_agent import PortfolioManagerAgent
from src.models.persistence import PersistenceManager

@pytest.mark.anyio
async def test_horizon_state_transition():
    db = PersistenceManager(":memory:")
    agent = PortfolioManagerAgent(db)
    
    user_id = "test_user"
    # Set a goal far in the future
    db.save_investment_goal(name="House", target_amount=50000, deadline=(datetime.now() + timedelta(days=1000)).strftime("%Y-%m-%d"))
    
    # Check initial horizon
    horizon = agent.get_current_horizon(user_id)
    assert horizon == "Long-Term"
    
    # Add a life event that shortens the horizon
    db.save_user_life_event(user_id, "Urgent Need", (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"), "Need cash soon")
    
    # Check updated horizon
    new_horizon = agent.get_current_horizon(user_id)
    assert new_horizon == "Short-Term"
