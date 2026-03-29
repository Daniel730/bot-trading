from typing import TypedDict, Annotated, List, Dict
from langgraph.graph import StateGraph, END
from src.agents.bull_agent import bull_agent
from src.agents.bear_agent import bear_agent
from src.agents.news_analyst import news_analyst

class AgentState(TypedDict):
    signal_context: dict
    bull_verdict: dict
    bear_verdict: dict
    news_verdict: dict
    final_confidence: float
    reasoning: str

async def bull_node(state: AgentState):
    verdict = await bull_agent.evaluate(state['signal_context'])
    return {"bull_verdict": verdict}

async def bear_node(state: AgentState):
    verdict = await bear_agent.evaluate(state['signal_context'])
    return {"bear_verdict": verdict}

async def news_node(state: AgentState):
    tickers = [state['signal_context']['ticker_a'], state['signal_context']['ticker_b']]
    verdict = await news_analyst.analyze_sentiment(tickers)
    return {"news_verdict": verdict}

async def aggregator_node(state: AgentState):
    # Consolidate agent outputs
    bull_conf = state['bull_verdict']['confidence']
    bear_conf = state['bear_verdict']['confidence']
    news_sentiment = state['news_verdict']['sentiment_score']
    
    if state['news_verdict']['event_spike']:
        return {"final_confidence": 0.0, "reasoning": "VETO: Fundamental Event Spike detected."}
    
    final_conf = (bull_conf + (1 - bear_conf) + (news_sentiment + 1)/2) / 3
    reasoning = f"Aggregated decision: Bull({bull_conf}), Bear({bear_conf}), News({news_sentiment})"
    
    return {"final_confidence": final_conf, "reasoning": reasoning}

def create_orchestrator():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("bull", bull_node)
    workflow.add_node("bear", bear_node)
    workflow.add_node("news", news_node)
    workflow.add_node("aggregator", aggregator_node)
    
    workflow.set_entry_point("bull") # Can run in parallel in LangGraph normally, simplified here
    workflow.add_edge("bull", "bear")
    workflow.add_edge("bear", "news")
    workflow.add_edge("news", "aggregator")
    workflow.add_edge("aggregator", END)
    
    return workflow.compile()

orchestrator = create_orchestrator()
