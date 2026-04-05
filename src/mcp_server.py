from fastmcp import FastMCP
from typing import List, Dict, Optional
import json
from src.config import settings
from src.services.redis_service import redis_service
from src.services.persistence_service import persistence_service, OrderSide

mcp = FastMCP("Arbitrage-Elite-Engine")

@mcp.tool()
async def get_market_data(tickers: List[str], source: str = "yfinance", lookback: str = "30d") -> str:
    """
    Fetches market data for specified tickers.
    """
    # Use Redis shadow book for latest prices if available
    prices = {}
    for ticker in tickers:
        price = await redis_service.get_price(ticker)
        if price:
            prices[ticker] = price
            
    return json.dumps({
        "status": "success",
        "prices": prices,
        "source": source
    })

@mcp.tool()
async def execute_trade(ticker: str, side: str, quantity: float, mode: str = "SHADOW") -> str:
    """
    Executes a trade and logs to persistence.
    """
    import uuid
    order_id = str(uuid.uuid4())
    
    # Log to PostgreSQL
    await persistence_service.log_trade({
        "order_id": order_id,
        "ticker": ticker,
        "side": OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
        "quantity": quantity,
        "price": 0.0, # Placeholder
        "metadata": {"mode": mode}
    })
    
    return json.dumps({
        "status": "success",
        "order_id": order_id
    })

@mcp.tool()
async def calculate_risk_metrics(confidence_score: float, portfolio: List[Dict] = None) -> str:
    """
    Computes position sizing and VaR.
    """
    # Implementation placeholder for T009
    return json.dumps({
        "suggested_size": 10.0,
        "var_95": 0.015
    })

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8000)
