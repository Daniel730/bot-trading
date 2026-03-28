import sqlite3
import asyncio
import logging
from fastmcp import FastMCP
from src.config import DB_PATH
from src.services.data_service import DataService
from src.services.notification_service import NotificationService
from src.models.arbitrage_models import AIValidationStatus

# Initialize MCP server
mcp = FastMCP("Strategic Arbitrage Engine")

# Services
data_service = DataService()
notification_service = NotificationService()

logger = logging.getLogger("MCPServer")

@mcp.tool()
async def analyze_news(tickers: list[str], headlines: list[str]) -> dict:
    """
    Analyzes news headlines for structural changes or technical noise.
    Used by Gemini to validate if a Z-score deviation is a tradeable opportunity.
    """
    # This tool is a placeholder for Gemini to provide its own analysis.
    # We return the context so Gemini can process it.
    return {
        "tickers": tickers,
        "headlines": headlines,
        "instruction": "Determine if these news indicate a structural change (GO/NO-GO)."
    }

@mcp.tool()
async def assess_risk(pair: str, z_score: float) -> dict:
    """
    Calculates estimated risk rating and max drawdown for a pair.
    """
    # Logic based on Z-score magnitude
    risk_rating = "LOW"
    if abs(z_score) > 3.5:
        risk_rating = "HIGH"
    elif abs(z_score) > 3.0:
        risk_rating = "MEDIUM"
        
    return {
        "pair": pair,
        "z_score": z_score,
        "risk_rating": risk_rating,
        "max_drawdown_est": abs(z_score) * 0.02 # Rough estimation
    }

@mcp.tool()
async def record_ai_decision(signal_id: str, status: str, rationale: str) -> str:
    """
    Records Gemini's decision (GO/NO_GO) and rationale in the database.
    Status must be 'GO' or 'NO_GO'.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        db_status = AIValidationStatus.GO if status.upper() == "GO" else AIValidationStatus.NO_GO
        
        cursor.execute(
            "UPDATE signal_records SET ai_validation_status = ?, ai_rationale = ? WHERE id = ?",
            (db_status.value, rationale, signal_id)
        )
        conn.commit()
        
        # If GO, trigger user confirmation via Telegram
        if db_status == AIValidationStatus.GO:
            # Fetch pair details for the notification
            cursor.execute(
                "SELECT ticker_a, ticker_b, z_score FROM signal_records sr JOIN arbitrage_pairs p ON sr.pair_id = p.id WHERE sr.id = ?",
                (signal_id,)
            )
            row = cursor.fetchone()
            if row:
                t_a, t_b, z = row
                await notification_service.send_confirmation_request(signal_id, f"{t_a}/{t_b}", z, rationale)
        
        conn.close()
        return f"Decision {db_status} recorded for signal {signal_id}."
    except Exception as e:
        logger.error(f"Failed to record AI decision: {e}")
        return f"Error: {str(e)}"

if __name__ == "__main__":
    mcp.run()
