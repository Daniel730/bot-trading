from typing import TypedDict, Annotated, List, Dict
import asyncio
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
        state: AgentState = {
            "signal_context": input_data["signal_context"],
            "bull_verdict": {},
            "bear_verdict": {},
            "fundamental_verdict": {},
            "final_confidence": 0.0,
            "final_verdict": ""
        }

        # 1. Parallel execution of Bull and Bear agents
        # (Assuming bull_agent and bear_agent are available in scope)
        bull_results, bear_results = await asyncio.gather(
            bull_agent.evaluate(state['signal_context']),
            bear_agent.evaluate(state['signal_context'])
        )
        state['bull_verdict'] = bull_results
        state['bear_verdict'] = bear_results

        # 2. Fundamental Analysis (SEC with News Fallback)
        ticker_a = state['signal_context']['ticker_a']
        ticker_b = state['signal_context']['ticker_b']
        signal_id = state['signal_context'].get('signal_id')

        # Analyze both tickers in the pair
        fundamental_results = await asyncio.gather(
            self.fundamental_analyst.analyze_ticker(signal_id, ticker_a),
            self.fundamental_analyst.analyze_ticker(signal_id, ticker_b)
        )
        
        f_signal_a, f_signal_b = fundamental_results
        
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
