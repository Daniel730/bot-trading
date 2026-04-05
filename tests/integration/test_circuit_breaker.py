import pytest
import asyncio
from unittest.mock import patch, MagicMock
from src.agents.orchestrator import Orchestrator
from src.models.persistence import PersistenceManager

@pytest.mark.asyncio
async def test_circuit_breaker_tripping():
    """
    T014: Verifies that Orchestrator trips to DEGRADED_MODE after 3 timeouts.
    """
    db = PersistenceManager(":memory:")
    # Seed db for test
    db.set_system_state("operational_status", "NORMAL")
    db.set_system_state("consecutive_api_timeouts", "0")
    
    # Patch Orchestrator's db access
    with patch('src.models.persistence.PersistenceManager', return_value=db):
        orchestrator = Orchestrator()
        
        input_data = {
            "signal_context": {"ticker_a": "AAPL", "ticker_b": "MSFT", "signal_id": "test_cb"}
        }
        
        # Mock agents to raise TimeoutError
        with patch('src.agents.orchestrator.bull_agent.evaluate', side_effect=asyncio.TimeoutError()):
            # Attempt 1
            await orchestrator.ainvoke(input_data)
            assert db.get_system_state("consecutive_api_timeouts") == "1"
            assert db.get_system_state("operational_status") == "NORMAL"
            
            # Attempt 2
            await orchestrator.ainvoke(input_data)
            assert db.get_system_state("consecutive_api_timeouts") == "2"
            
            # Attempt 3 - Should trip
            await orchestrator.ainvoke(input_data)
            assert db.get_system_state("consecutive_api_timeouts") == "3"
            assert db.get_system_state("operational_status") == "DEGRADED_MODE"
            
            # Attempt 4 - Should be blocked immediately
            result = await orchestrator.ainvoke(input_data)
            assert result["final_confidence"] == 0.0
            assert "DEGRADED_MODE" in result["final_verdict"]

@pytest.mark.asyncio
async def test_circuit_breaker_reset():
    """
    Verifies that successful execution resets the timeout count.
    """
    db = PersistenceManager(":memory:")
    db.set_system_state("consecutive_api_timeouts", "2")
    
    with patch('src.models.persistence.PersistenceManager', return_value=db):
        orchestrator = Orchestrator()
        
        # Mock successful evaluation
        with patch('src.agents.orchestrator.bull_agent.evaluate', return_value={"confidence": 0.5}):
            with patch('src.agents.orchestrator.bear_agent.evaluate', return_value={"confidence": 0.5}):
                with patch('src.agents.orchestrator.orchestrator.fundamental_analyst.analyze_ticker'):
                    await orchestrator.ainvoke({"signal_context": {"ticker_a": "X", "ticker_b": "Y"}})
                    assert db.get_system_state("consecutive_api_timeouts") == "0"

if __name__ == "__main__":
    asyncio.run(test_circuit_breaker_tripping())
    asyncio.run(test_circuit_breaker_reset())
