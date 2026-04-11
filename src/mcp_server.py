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
    Executes a trade via gRPC to the Java Engine and logs to persistence.
    """
    import uuid
    from src.generated.execution_pb2 import STATUS_SUCCESS
    
    signal_id = str(uuid.uuid4())
    
    # Define legs (for a single trade tool, we create one leg)
    legs = [{
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "target_price": 0.0 # Will be calculated by Engine if 0
    }]
    
    # Execute via gRPC
    response = await execution_client.execute_trade(
        signal_id=signal_id,
        pair_id=pair_id,
        legs=legs
    )
    
    status = "error"
    if response:
        status = "success" if response.status == STATUS_SUCCESS else "rejected"
    
    # Log to PostgreSQL (backward compatibility)
    await persistence_service.log_trade({
        "order_id": signal_id,
        "ticker": ticker,
        "side": OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
        "quantity": quantity,
        "price": response.actual_vwap if response else 0.0,
        "metadata": {
            "mode": mode,
            "grpc_status": str(response.status) if response else "failed",
            "message": response.message if response else "No response"
        }
    })
    
    return json.dumps({
        "status": status,
        "signal_id": signal_id,
        "response_message": response.message if response else "No response from Engine"
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
