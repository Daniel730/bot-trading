from typing import TypedDict, Annotated, List, Dict
from langgraph.graph import StateGraph, END
from src.agents.bull_agent import bull_agent
from src.agents.bear_agent import bear_agent
from src.agents.fundamental_analyst import fundamental_analyst

class AgentState(TypedDict):
    signal_context: dict
    bull_verdict: dict
    bear_verdict: dict
    fundamental_verdict: dict # Feature 009: Replacing news with SEC Fundamental Analysis
    final_confidence: float
    reasoning: str

async def bull_node(state: AgentState):
    verdict = await bull_agent.evaluate(state['signal_context'])
    return {"bull_verdict": verdict}

async def bear_node(state: AgentState):
    verdict = await bear_agent.evaluate(state['signal_context'])
    return {"bear_verdict": verdict}

async def fundamental_node(state: AgentState):
    """Feature 009: Analyzes SEC filings for both tickers in the pair."""
    # Note: For efficiency in this MVP, we analyze Ticker A (the primary signal mover)
    ticker = state['signal_context']['ticker_a']
    sec_sections = state['signal_context'].get('sec_sections', {})
    
    verdict = await fundamental_analyst.analyze_structural_integrity(ticker, sec_sections)
    return {"fundamental_verdict": verdict}

async def aggregator_node(state: AgentState):
    # Consolidate agent outputs
    bull_conf = state['bull_verdict']['confidence']
    bear_conf = state['bear_verdict']['confidence']
    
    # Feature 009: High-weight fundamental analysis
    f_verdict = state['fundamental_verdict']
    integrity_score = f_verdict['integrity_score'] / 100.0
    
    # Absolute VETO if fundamental analyst recommends NO-GO
    if f_verdict['recommendation'] == "NO-GO" or integrity_score < 0.4:
        return {"final_confidence": 0.0, "reasoning": f"VETO: {f_verdict['rationale']}"}
    
    # Weighted average: Bull, Bear, and Fundamental Integrity
    final_conf = (bull_conf + (1 - bear_conf) + integrity_score) / 3
    reasoning = f"Aggregated: Bull({bull_conf}), Bear({bear_conf}), SEC-Integrity({integrity_score:.2f})"
    
    return {"final_confidence": final_conf, "reasoning": reasoning}

def create_orchestrator():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("bull", bull_node)
    workflow.add_node("bear", bear_node)
    workflow.add_node("fundamental", fundamental_node)
    workflow.add_node("aggregator", aggregator_node)
    
    workflow.set_entry_point("bull")
    workflow.add_edge("bull", "bear")
    workflow.add_edge("bear", "fundamental")
    workflow.add_edge("fundamental", "aggregator")
    workflow.add_edge("aggregator", END)
    
    return workflow.compile()

orchestrator = create_orchestrator()
