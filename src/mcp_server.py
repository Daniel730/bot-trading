from fastmcp import FastMCP
from typing import List, Dict
import json
from src.services.redis_service import redis_service
from src.services.persistence_service import persistence_service, OrderSide
from src.services.execution_service_client import execution_client

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
async def execute_trade(ticker: str, side: str, quantity: float, mode: str = "SHADOW", pair_id: str = "MANUAL") -> str:
    """
    Rejects direct FastMCP trade execution until it can share the main bot safety path.
    """
    return json.dumps({
        "status": "rejected",
        "reason": (
            "FastMCP execute_trade is disabled; use the dashboard/monitor "
            "execution workflow so paper/live, risk, and reconciliation gates run."
        ),
        "mode": mode,
        "pair_id": pair_id,
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
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
