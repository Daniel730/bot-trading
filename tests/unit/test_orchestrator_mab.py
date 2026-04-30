import pytest
import sys
import os

# Ensure src is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from unittest.mock import patch, MagicMock
from src.agents.orchestrator import orchestrator

@pytest.mark.asyncio
async def test_thompson_sampling_weight_allocation():
    """
    Test F1: Validates that Thompson Sampling correctly biases decisions 
    towards historically successful agents (Multi-Armed Bandit logic).
    """
    input_data = {
        "signal_context": {
            "signal_id": "test_mab_signal_1",
            "ticker_a": "AAPL",
            "ticker_b": "GOOG",
            "hedge_ratio": 1.0,
            "z_score": 2.5
        }
    }

    # Helper function to return simulated MAB successes and failures
    async def mock_get_agent_metrics(agent_name):
        if agent_name == "SEC_AGENT":
            return (1000, 1) # Highly successful agent (Beta alpha must be > 0, beta must be > 0)
        return (1, 1000)     # Highly failed agents (BULL and BEAR)

    # Side effect function to handle multiple keys
    async def mock_get_system_state(key, default=None):
        if key == "operational_status":
            return "NORMAL"
        if key == "consecutive_api_timeouts":
            return "0"
        return default

    # We patch all the external API calls and the new Thompson DB fetcher.
    # Macro regime + portfolio advice must be mocked too — otherwise Phase 0
    # makes real yfinance calls for the sector beacon (NVDA), which can return
    # EXTREME_VOLATILITY and short-circuit the orchestrator before MAB runs.
    with patch('src.agents.bull_agent.BullAgent.evaluate', return_value={"confidence": 0.1, "reasoning": "bad"}), \
         patch('src.agents.bear_agent.BearAgent.evaluate', return_value={"confidence": 0.9, "reasoning": "bad"}), \
         patch('src.services.redis_service.RedisService.get_fundamental_score', return_value={"score": 100}), \
         patch('src.services.persistence_service.PersistenceService.get_system_state', side_effect=mock_get_system_state), \
         patch('src.services.persistence_service.PersistenceService.get_agent_metrics', side_effect=mock_get_agent_metrics), \
         patch('src.services.persistence_service.PersistenceService.set_system_state'), \
         patch('src.agents.macro_economic_agent.MacroEconomicAgent.get_ticker_regime', return_value="BULLISH"), \
         patch('src.agents.portfolio_manager_agent.PortfolioManagerAgent.get_optimization_advice', return_value={"is_recommended": True, "improvement": 0.0}):

        # Execute the orchestrator
        state = await orchestrator.ainvoke(input_data)
        
        # In our mocked scenario:
        # Bull is 0.1, Bear is 0.9 (invert is 0.1). SEC is 100 on both so 100/100 = 1.0.
        # But SEC has 1000 successes! So SEC's weight (w_sec) should be extremely close to 1.0 (> 0.95).
        # Therefore, the final confidence should perfectly mimic the SEC score (1.0), 
        # ignoring the terrible Bull and Bear confident outputs.
        
        # Verify the MAB weighting reflects in the string
        assert "MAB Weighted" in state["final_verdict"], "Orchestrator did not use Thompson Sampling format."
        
        # Extract w_sec from the string manually or just check final confidence > 0.95
        # Since Bull/Bear contribute 0.1 and SEC contributes 1.0
        # If w_sec approaches 1.0, final_conf approaches 1.0.
        assert state["final_confidence"] > 0.95, f"MAB did not correctly exploit SEC agent's historic success. Confidence: {state['final_confidence']}"
