import pytest
import asyncio
from unittest.mock import MagicMock, patch
from src.agents.orchestrator import Orchestrator

@pytest.mark.asyncio
async def test_orchestrator_resilience_to_agent_failure():
    """
    T015: Verifies that Orchestrator.ainvoke survives when one of the agents
    in asyncio.gather raises an exception.
    """
    orchestrator = Orchestrator()
    
    # Mock agents: Bull succeeds, Bear fails
    mock_bull_result = {"confidence": 0.8, "signals": []}
    
    input_data = {
        "signal_context": {
            "ticker_a": "AAPL",
            "ticker_b": "MSFT",
            "signal_id": "test_123"
        }
    }

    with patch('src.agents.orchestrator.bull_agent.evaluate', return_value=mock_bull_result):
        with patch('src.agents.orchestrator.bear_agent.evaluate', side_effect=Exception("Bear Agent Crash!")):
            # If implementation is correct (return_exceptions=True), this should not raise Exception
            try:
                result = await orchestrator.ainvoke(input_data)
                
                # Check that bull verdict was captured
                assert result['bull_verdict'] == mock_bull_result
                # Check that bear verdict contains the error info
                assert isinstance(result['bear_verdict'], dict)
                assert "error" in result['bear_verdict']
                assert "Bear Agent Crash!" in result['bear_verdict']['error']
                
            except Exception as e:
                pytest.fail(f"Orchestrator crashed with exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_orchestrator_resilience_to_agent_failure())
