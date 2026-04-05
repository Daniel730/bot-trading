from typing import TypedDict, Annotated, List, Dict
import asyncio
from unittest.mock import MagicMock
from src.agents.bull_agent import bull_agent
from src.agents.bear_agent import bear_agent
from src.agents.fundamental_analyst import FundamentalAnalyst
from src.services.sec_service import SECService

class Orchestrator:
    """
    Refactored Orchestrator that executes the multi-agent debate 
    without requiring the langgraph library.
    """
    def __init__(self):
        self.fundamental_analyst = FundamentalAnalyst()

    async def ainvoke(self, input_data: dict) -> dict:
        from src.models.persistence import PersistenceManager
        db = PersistenceManager()
        
        # FR-004: Block new entries if in DEGRADED_MODE
        operational_status = db.get_system_state("operational_status", "NORMAL")
        
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
        results = await asyncio.gather(
            bull_agent.evaluate(state['signal_context']),
            bear_agent.evaluate(state['signal_context']),
            return_exceptions=True
        )
        
        bull_results, bear_results = results
        
        # Track if any major API timeout occurred for circuit breaker (FR-003)
        timeout_occurred = False
        
        if isinstance(bull_results, Exception):
            print(f"AGENT_LOGGER: Orchestrator Bull Agent failed: {bull_results}")
            if isinstance(bull_results, asyncio.TimeoutError): timeout_occurred = True
            state['bull_verdict'] = {"confidence": 0.0, "error": str(bull_results)}
        else:
            state['bull_verdict'] = bull_results
            
        if isinstance(bear_results, Exception):
            print(f"AGENT_LOGGER: Orchestrator Bear Agent failed: {bear_results}")
            if isinstance(bear_results, asyncio.TimeoutError): timeout_occurred = True
            state['bear_verdict'] = {"confidence": 0.0, "error": str(bear_results)}
        else:
            state['bear_verdict'] = bear_results

        # 2. Fundamental Analysis (SEC with News Fallback)
        ticker_a = state['signal_context']['ticker_a']
        ticker_b = state['signal_context']['ticker_b']
        signal_id = state['signal_context'].get('signal_id')

        # Analyze both tickers in the pair with resilience
        fundamental_results = await asyncio.gather(
            self.fundamental_analyst.analyze_ticker(signal_id, ticker_a),
            self.fundamental_analyst.analyze_ticker(signal_id, ticker_b),
            return_exceptions=True
        )
        
        # Filter out exceptions from fundamental results for scoring
        valid_fundamental_results = []
        for i, res in enumerate(fundamental_results):
            ticker = ticker_a if i == 0 else ticker_b
            if isinstance(res, Exception):
                print(f"AGENT_LOGGER: Orchestrator Fundamental analysis failed for {ticker}: {res}")
                if isinstance(res, asyncio.TimeoutError): timeout_occurred = True
                # Create a fallback signal with neutral score
                class MockSignal:
                    def __init__(self, score): self.structural_integrity_score = score
                valid_fundamental_results.append(MockSignal(50))
            else:
                valid_fundamental_results.append(res)
        
        f_signal_a, f_signal_b = valid_fundamental_results
        
        # FR-003: Circuit Breaker Logic (Persistent)
        consecutive_timeouts = int(db.get_system_state("consecutive_api_timeouts", "0"))
        
        if timeout_occurred:
            consecutive_timeouts += 1
            db.set_system_state("consecutive_api_timeouts", str(consecutive_timeouts))
            if consecutive_timeouts >= 3:
                db.set_system_state("operational_status", "DEGRADED_MODE")
                print("AGENT_LOGGER: CRITICAL - Circuit Breaker Tripped! Entering DEGRADED_MODE.")
        else:
            # Reset on full successful loop
            db.set_system_state("consecutive_api_timeouts", "0")
        
        # 3. Aggregation Logic with VETO
        bull_conf = state['bull_verdict']['confidence']
        bear_conf = state['bear_verdict']['confidence']
        
        score_a = f_signal_a.structural_integrity_score
        score_b = f_signal_b.structural_integrity_score
        
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
