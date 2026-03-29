from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import sqlite3
import logging
from typing import List, Dict, Any
from src.config import LOG_LEVEL

# Configure logging
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# Define CORS middleware
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )
]

# Initialize FastMCP server with middleware
mcp = FastMCP("Strategic Arbitrage Server", middleware=middleware)

@mcp.tool()
def analyze_news(tickers: List[str], headlines: List[str]) -> Dict[str, Any]:
    """
    Called by the bot to validate signals via Gemini CLI.
    Simulates AI analysis of news for fundamental validation.
    """
    logger.info(f"AI Analyzing news for {tickers}")
    return {
        "recommendation": "GO",
        "sentiment_score": 0.85,
        "rationale": "Strong positive sentiment and no structural breaks detected in recent filings."
    }

@mcp.tool()
def record_ai_decision(signal_id: str, status: str, rationale: str) -> str:
    """
    Called by Gemini CLI to persist its logic back to the bot.
    """
    try:
        conn = sqlite3.connect("trading_bot.sqlite")
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE SignalRecord 
            SET ai_validation_status = ?, ai_rationale = ?
            WHERE id = ?
        ''', (status, rationale, signal_id))
        conn.commit()
        conn.close()
        logger.info(f"AI decision recorded for signal {signal_id}: {status}")
        return f"Successfully recorded AI decision for {signal_id}"
    except Exception as e:
        logger.error(f"Failed to record AI decision: {e}")
        return f"Error: {e}"

if __name__ == "__main__":
    # Start FastMCP server with SSE transport on 0.0.0.0:8000
    mcp.run(transport="sse", host="0.0.0.0", port=8000)
