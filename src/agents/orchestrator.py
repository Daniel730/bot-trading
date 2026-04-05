from typing import TypedDict, Annotated, List, Dict
import asyncio
from unittest.mock import MagicMock
from src.agents.bull_agent import bull_agent
from src.agents.bear_agent import bear_agent
from src.services.redis_service import redis_service
from src.services.telemetry_service import telemetry_service

class AgentState(TypedDict):
    signal_context: dict
    bull_verdict: dict
    bear_verdict: dict
    fundamental_verdict: dict
    final_confidence: float
    final_verdict: str

class Orchestrator:
    """
    Refactored Orchestrator that executes the multi-agent debate 
    without requiring the langgraph library.
    Now uses cached fundamental scores to avoid high latency RAG calls.
    """
    def __init__(self):
        # We no longer need to instantiate FundamentalAnalyst here
        # as analysis happens in the background daemon.
        pass

    async def ainvoke(self, input_data: dict) -> dict:
        from src.services.persistence_service import persistence_service
        
        # FR-004: Block new entries if in DEGRADED_MODE
        operational_status = await persistence_service.get_system_state("operational_status", "NORMAL")
        
        state: AgentState = {
            "signal_context": input_data["signal_context"],
            "bull_verdict": {},
            "bear_verdict": {},
            "fundamental_verdict": {},
            "final_confidence": 0.0,
            "final_verdict": ""
        }

        if operational_status == "DEGRADED_MODE":
            state["final_confidence"] = 0.0
            state["final_verdict"] = "VETO: DEGRADED_MODE active due to consecutive API failures. Entry blocked."
            return state

        # 1. Parallel execution of Bull and Bear agents with resilience
        # AND Parallel retrieval of fundamental scores from Redis (US1)
        ticker_a = state['signal_context']['ticker_a']
        ticker_b = state['signal_context']['ticker_b']
        
        results = await asyncio.gather(
            bull_agent.evaluate(state['signal_context']),
            bear_agent.evaluate(state['signal_context']),
            redis_service.get_fundamental_score(ticker_a),
            redis_service.get_fundamental_score(ticker_b),
            return_exceptions=True
        )
        
        bull_results, bear_results, score_data_a, score_data_b = results
        
        # Track if any major API timeout occurred for circuit breaker
        timeout_occurred = False
        
        # Handle Bull Agent results
        if isinstance(bull_results, Exception):
            print(f"AGENT_LOGGER: Orchestrator Bull Agent failed: {bull_results}")
            if isinstance(bull_results, asyncio.TimeoutError): timeout_occurred = True
            state['bull_verdict'] = {"confidence": 0.0, "error": str(bull_results)}
        else:
            state['bull_verdict'] = bull_results
            
        # Handle Bear Agent results
        if isinstance(bear_results, Exception):
            print(f"AGENT_LOGGER: Orchestrator Bear Agent failed: {bear_results}")
            if isinstance(bear_results, asyncio.TimeoutError): timeout_occurred = True
            state['bear_verdict'] = {"confidence": 0.0, "error": str(bear_results)}
        else:
            state['bear_verdict'] = bear_results

        # Handle Fundamental Score A (Redis)
        score_a = 50
        if isinstance(score_data_a, Exception):
            print(f"AGENT_LOGGER: Orchestrator Redis read failed for {ticker_a}: {score_data_a}")
        elif score_data_a:
            score_a = score_data_a.get("score", 50)
        else:
            print(f"AGENT_LOGGER: CRITICAL - Fundamental cache miss for {ticker_a}. Defaulting to 50.")
            await telemetry_service.log_event("fundamental_cache_miss", {"ticker": ticker_a, "priority": "HIGH"})
            
        # Handle Fundamental Score B (Redis)
        score_b = 50
        if isinstance(score_data_b, Exception):
            print(f"AGENT_LOGGER: Orchestrator Redis read failed for {ticker_b}: {score_data_b}")
        elif score_data_b:
            score_b = score_data_b.get("score", 50)
        else:
            print(f"AGENT_LOGGER: CRITICAL - Fundamental cache miss for {ticker_b}. Defaulting to 50.")
            await telemetry_service.log_event("fundamental_cache_miss", {"ticker": ticker_b, "priority": "HIGH"})
        
        # FR-003: Circuit Breaker Logic (Persistent)
        consecutive_timeouts_str = await persistence_service.get_system_state("consecutive_api_timeouts", "0")
        consecutive_timeouts = int(consecutive_timeouts_str)
        
        if timeout_occurred:
            consecutive_timeouts += 1
            await persistence_service.set_system_state("consecutive_api_timeouts", str(consecutive_timeouts))
            if consecutive_timeouts >= 3:
                await persistence_service.set_system_state("operational_status", "DEGRADED_MODE")
                print("AGENT_LOGGER: CRITICAL - Circuit Breaker Tripped! Entering DEGRADED_MODE.")
        else:
            # Reset on full successful loop
            await persistence_service.set_system_state("consecutive_api_timeouts", "0")
        
        # 3. Aggregation Logic with VETO
        bull_conf = state['bull_verdict']['confidence']
        bear_conf = state['bear_verdict']['confidence']
        
        # Absolute VETO if structural integrity score < 40 for either ticker
        if score_a < 40 or score_b < 40:
            state["final_confidence"] = 0.0
            veto_reason = f"VETO: Low Structural Integrity. {ticker_a}: {score_a}, {ticker_b}: {score_b}"
            state["final_verdict"] = veto_reason
        else:
            # Combined score: average of structural integrity and bull/bear sentiment
            avg_integrity = (score_a + score_b) / 200.0
            final_conf = (bull_conf + (1 - bear_conf) + avg_integrity) / 3
            state["final_confidence"] = final_conf
            state["final_verdict"] = f"Aggregated: Bull({bull_conf:.2f}), Bear({bear_conf:.2f}), SEC-Avg-Integrity({avg_integrity:.2f})"
        
        return state

orchestrator = Orchestrator()
