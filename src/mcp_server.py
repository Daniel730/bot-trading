from fastmcp import FastMCP
from src.services.data_service import DataService
from src.services.notification_service import NotificationService
from src.config import DB_PATH
import sqlite3
import logging
from datetime import datetime
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("Trading Arbitrage Bot")

# Services
# We initialize them lazily or here if they don't depend on complex state
data_service = DataService()
notification_service = NotificationService()

@mcp.tool()
def get_market_prices(tickers: list[str]) -> str:
    """
    Fetches current market prices for a list of tickers.
    """
    logger.info(f"Fetching prices for: {tickers}")
    try:
        prices = data_service.get_current_prices(tickers)
        return str(prices)
    except Exception as e:
        logger.error(f"Error fetching prices: {e}")
        return f"Error: {str(e)}"

@mcp.tool()
def get_news_context(tickers: list[str]) -> str:
    """
    Retrieves recent news headlines for the specified tickers to validate arbitrage signals.
    """
    logger.info(f"Fetching news for: {tickers}")
    try:
        news = data_service.get_news_context(tickers)
        headlines = []
        for item in news:
            title = item.get('title')
            published = item.get('published_utc')
            headlines.append(f"- {title} ({published})")
        return "\n".join(headlines) if headlines else "No recent news found."
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        return f"Error: {str(e)}"

@mcp.tool()
def execute_arbitrage_trade(signal_id: str, ai_action: str, rationale: str) -> str:
    """
    Analyzes an arbitrage signal based on AI validation.
    ai_action MUST be 'GO' (to proceed to user confirmation) or 'NO-GO' (to reject).
    rationale should provide the reason for the decision based on news context.
    """
    logger.info(f"AI Action for signal {signal_id}: {ai_action}")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if signal exists and get its creation timestamp for duration calculation
        cursor.execute("SELECT pair_id, z_score, timestamp FROM signals WHERE id = ?", (signal_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return f"Error: Signal {signal_id} not found."
        
        pair_id, z_score, signal_timestamp_str = row
        
        # Calculate validation duration (SC-002)
        signal_timestamp = datetime.fromisoformat(signal_timestamp_str)
        duration = (datetime.now() - signal_timestamp).total_seconds()
        logger.info(f"AI Validation Duration for {signal_id}: {duration:.2f}s")
        
        # Log the AI recommendation in audit_logs
        cursor.execute("""
            INSERT INTO audit_logs (timestamp, signal_id, ai_recommendation, ai_rationale, action_taken, ai_validation_duration)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), signal_id, ai_action, rationale, "WAIT" if ai_action == "GO" else "CANCELLED", duration))
        
        if ai_action == "GO":
            # Update signal status
            cursor.execute("UPDATE signals SET status = ? WHERE id = ?", ("PENDING_USER_CONFIRM", signal_id))
            conn.commit()
            conn.close()
            
            # Send Telegram confirmation request to the user
            success = notification_service.send_confirmation_request(signal_id, pair_id, z_score, rationale)
            if success:
                return f"SUCCESS: Signal {signal_id} validated by AI. Telegram confirmation request sent to user. Rationale: {rationale}"
            else:
                return f"WARNING: Signal {signal_id} validated by AI, but failed to send Telegram notification. Rationale: {rationale}"
        else:
            # Update signal status to REJECTED
            cursor.execute("UPDATE signals SET status = ? WHERE id = ?", ("REJECTED", signal_id))
            conn.commit()
            conn.close()
            return f"SIGNAL REJECTED: Signal {signal_id} was marked NO-GO by AI. Reason: {rationale}"
            
    except Exception as e:
        logger.error(f"Error in execute_arbitrage_trade: {e}")
        return f"Error executing trade validation: {str(e)}"

@mcp.tool()
def get_virtual_pie_status() -> str:
    """
    Returns the current status of the Virtual Pie (target weights and current quantities).
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT ticker, target_weight, current_quantity, last_price FROM virtual_pie")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return "Virtual Pie is empty or not initialized."
            
        status = ["Ticker | Target % | Quantity | Last Price"]
        for row in rows:
            ticker, weight, qty, price = row
            status.append(f"{ticker} | {weight:.1%} | {qty:.4f} | ${price:.2f}")
        
        return "\n".join(status)
    except Exception as e:
        return f"Error fetching pie status: {str(e)}"

if __name__ == "__main__":
    mcp.run()
