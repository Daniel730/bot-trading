import yfinance as yf
import pandas as pd
from polygon import RESTClient
from typing import List, Optional
from src.config import settings
import asyncio
from src.services.agent_log_service import agent_trace

from src.services.redis_service import redis_service
from polygon.websocket import WebSocketClient
from polygon.websocket.models import Market, Feed

class DataService:
    def __init__(self):
        self.polygon_client = RESTClient(api_key=settings.POLYGON_API_KEY)
        self._ws_client: Optional[WebSocketClient] = None

    @agent_trace("DataService.get_historical_data")
    def get_historical_data(self, tickers: List[str], period: str = "30d", interval: str = "1h") -> pd.DataFrame:
        """
        Fetches historical data using yfinance with fallback to 'Close'.
        """
        try:
            df = yf.download(tickers, period=period, interval=interval, progress=False)
            if df.empty:
                raise ValueError(f"No data returned for {tickers}")
            
            # Handle multi-index columns if multiple tickers, or single index if one
            if 'Adj Close' in df.columns:
                return df['Adj Close']
            elif 'Close' in df.columns:
                return df['Close']
            else:
                # In some cases yf returns a flat DF with columns like 'Adj Close_KO'
                cols = [c for c in df.columns if 'Adj Close' in c or 'Close' in c]
                if cols:
                    return df[cols]
                raise KeyError(f"Neither 'Adj Close' nor 'Close' found in columns: {df.columns}")
        except Exception as e:
            print(f"DEBUG: yfinance error for {tickers}: {e}")
            raise

    @agent_trace("DataService.get_latest_price")
    def get_latest_price(self, tickers: List[str]) -> dict:
        """
        Fetches the latest prices for given tickers. 
        Tries Redis shadow book first, falls back to yfinance.
        """
        latest = {}
        remaining_tickers = []

        # 1. Try Redis Shadow Book
        for ticker in tickers:
            price = redis_service.get_price(ticker)
            if price:
                latest[ticker] = price
            else:
                remaining_tickers.append(ticker)

        if not remaining_tickers:
            return latest

        # 2. Fallback to yfinance for remaining
        try:
            df = yf.download(remaining_tickers, period="1d", interval="1m", progress=False)
            if df.empty:
                return latest
            
            import random
            # Handle multi-index (multiple tickers) or flat (single ticker)
            if len(remaining_tickers) > 1:
                for ticker in remaining_tickers:
                    if ticker in df['Close'].columns:
                        val = df['Close'][ticker].iloc[-1]
                        if not pd.isna(val):
                            if settings.DEV_MODE:
                                val = float(val) * (1 + random.uniform(-0.015, 0.015))
                            latest[ticker] = float(val)
                            # Cache in Redis
                            redis_service.set_price(ticker, float(val))
            else:
                ticker = remaining_tickers[0]
                val = df['Close'].iloc[-1]
                if not pd.isna(val):
                    if settings.DEV_MODE:
                        val = float(val) * (1 + random.uniform(-0.015, 0.015))
                    latest[ticker] = float(val)
                    # Cache in Redis
                    redis_service.set_price(ticker, float(val))
            return latest
        except Exception as e:
            print(f"DEBUG: yfinance error for latest price {remaining_tickers}: {e}")
            return latest

    @agent_trace("DataService.stream_realtime_data")
    async def stream_realtime_data(self, tickers: List[str]):
        """
        Connects to Polygon WebSocket to stream real-time prices into Redis.
        """
        def handle_msg(msgs):
            for m in msgs:
                # Trade event (T) or Quote event (Q)
                if hasattr(m, 'price'):
                    redis_service.set_price(m.symbol, m.price)
                elif hasattr(m, 'bid_price'):
                    # Mid-price approximation
                    mid = (m.bid_price + m.ask_price) / 2
                    redis_service.set_price(m.symbol, mid)

        # Polygon WebSocket implementation
        self._ws_client = WebSocketClient(
            api_key=settings.POLYGON_API_KEY,
            feed=Feed.Delayed, # Use Delayed for free tier, RealTime for paid
            market=Market.Stocks,
            subscriptions=[f"T.{t}" for t in tickers] + [f"Q.{t}" for t in tickers]
        )
        
        # Start processing in background or current loop
        # Note: This is a simplified version; real usage might need a separate thread/task
        await self._ws_client.run(handle_msg)

data_service = DataService()
