import pytest
from src.agents.macro_economic_agent import MacroEconomicAgent

def test_macro_agent_risk_on_signal():
    agent = MacroEconomicAgent()
    
    # Low rates, low inflation -> Risk On
    signal = agent.analyze_market_state(interest_rate=0.03, inflation=0.02)
    assert signal == "RISK_ON"

def test_macro_agent_risk_off_signal():
    agent = MacroEconomicAgent()
    
    # High rates or high inflation -> Risk Off
    signal = agent.analyze_market_state(interest_rate=0.06, inflation=0.05)
    assert signal == "RISK_OFF"

def test_threshold_logic():
    agent = MacroEconomicAgent(rate_threshold=0.05, inflation_threshold=0.04)
    
    assert agent.analyze_market_state(0.04, 0.03) == "RISK_ON"
    assert agent.analyze_market_state(0.051, 0.03) == "RISK_OFF"
