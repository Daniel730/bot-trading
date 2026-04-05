import pytest
import asyncio
from src.agents.portfolio_manager_agent import portfolio_manager
from src.agents.macro_economic_agent import macro_economic_agent
from src.models.persistence import PersistenceManager
from src.config import settings
from unittest.mock import patch, MagicMock

def test_thesis_generation_with_logs():
    persistence = PersistenceManager(settings.DB_PATH)
    
    # 1. Seed a log and a thought journal
    ticker = "AAPL"
    signal_id = "test-signal-123"
    
    persistence.log_event("INFO", "FRACTIONAL_ENGINE", f"Executed BUY for {ticker}", {"ticker": ticker})
    # Update the signal_id for that log manually since log_event generates a new uuid
    with persistence._get_connection() as conn:
        conn.execute("UPDATE logs SET signal_id = ? WHERE source = 'FRACTIONAL_ENGINE'", (signal_id,))
        conn.commit()
        
    persistence.log_thought(
        signal_id=signal_id,
        bull="Strong demand for iPhone",
        bear="High valuation",
        news="Buffett buys more",
        verdict="GO"
    )
    
    # 2. Generate thesis
    thesis = asyncio.run(portfolio_manager.generate_investment_thesis(ticker))
    
    # 3. Verify content
    assert "🛡️ **Investment Thesis for AAPL**" in thesis
    assert "Strong demand" in thesis
    assert "Buffett buys" in thesis
    assert "test-signal-123" in thesis

def test_macro_summary_format():
    summary = {
        "yield_10y": 4.2,
        "vix": 15.0,
        "market_trend": "Bullish",
        "spy_curr": 500.0,
        "spy_50d": 480.0,
        "risk_on": True
    }
    
    msg = macro_economic_agent.format_summary_for_telegram(summary)
    assert "🌐 **Macro Economic Summary**" in msg
    assert "🟢 RISK-ON" in msg
    assert "10Y Yield: 4.20%" in msg
