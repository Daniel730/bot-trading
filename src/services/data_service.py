import logging
import yfinance as yf
import pandas as pd
import requests
from polygon import RESTClient
from typing import List, Optional
from src.config import settings
import asyncio
from src.services.agent_log_service import agent_trace

logger = logging.getLogger(__name__)

class AwaitableDict(dict):
    def __await__(self):
        async def _coro():
            return self
        return _coro().__await__()

from src.services.redis_service import redis_service
from polygon.websocket import WebSocketClient
from polygon.websocket.models import Market, Feed
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

class DataService:
    def __init__(self):
        self.polygon_client = RESTClient(api_key=settings.POLYGON_API_KEY)
        self._ws_client: Optional[WebSocketClient] = None

    @agent_trace("DataService.get_historical_data")
    def get_historical_data(self, tickers: List[str], period: str = "30d", interval: str = "1h") -> pd.DataFrame:
        """
        Fetches historical data using yfinance with auto_adjust=True.
        """
        try:
            # Bug 1.2: Enforce auto_adjust=True to handle splits and dividends correctly
            df = yf.download(tickers, period=period, interval=interval, progress=False, auto_adjust=True)
            if df.empty:
                raise ValueError(f"No data returned for {tickers}")
            
            # When auto_adjust=True, 'Adj Close' is usually not present, 'Close' IS the adjusted close
            if 'Close' in df.columns:
                return df['Close']
            else:
                # In some cases yf returns a flat DF
                cols = [c for c in df.columns if 'Close' in c]
                if cols:
                    return df[cols]
                raise KeyError(f"Adjusted 'Close' not found in columns: {df.columns}")
        except Exception as e:
            logger.error(f"DataService: yfinance error for {tickers}: {e}")
            raise

    @agent_trace("DataService.get_latest_price")
    def get_latest_price(self, tickers: List[str]) -> dict:
        """
        Fetches the latest prices for given tickers.
        Tries Redis shadow book first, falls back to yfinance with retries.
        Decision 1: Uses tenacity for 3-attempt exponential backoff.
        """
        latest = {}
        remaining_tickers = []

        # 1. Try Redis Shadow Book
        for ticker in tickers:
            price = None
            try:
                candidate = redis_service.get_price(ticker)
                if not asyncio.iscoroutine(candidate):
                    price = candidate
                else:
                    candidate.close()
            except Exception:
                price = None
            if price:
                latest[ticker] = price
            else:
                remaining_tickers.append(ticker)

        if not remaining_tickers:
            return latest

        # 2. Fallback to yfinance for remaining with retry logic
        try:
            yfinance_prices = self._get_latest_price_yfinance_with_retry(remaining_tickers)
            for ticker, price in yfinance_prices.items():
                try:
                    stored = redis_service.set_price(ticker, price)
                    if asyncio.iscoroutine(stored):
                        stored.close()
                except Exception:
                    pass
            latest.update(yfinance_prices)
        except Exception as e:
            logger.error(f"DataService: retry failed after 3 attempts for {remaining_tickers}: {e}")
            
        return AwaitableDict(latest)

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=4), 
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    def _get_latest_price_yfinance_with_retry(self, tickers: List[str]) -> dict:
        """Internal helper to fetch prices from yfinance with tenacity retries."""
        results = {}
        
        # US-035: Per-ticker fetch is more robust against crumb/auth errors than batch download
        import time
        for ticker in tickers:
            try:
                df = yf.download(ticker, period="1d", interval="1m", progress=False, auto_adjust=True)
                if not df.empty:
                    val = df['Close'].iloc[-1]
                    if not pd.isna(val):
                        # Apply DEV_MODE randomization if active
                        if settings.DEV_MODE:
                            import random
                            val = float(val) * (1 + random.uniform(-0.015, 0.015))
                        results[ticker] = float(val)
                # Small delay to prevent Yahoo from flagging the IP
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"DataService: Error fetching {ticker} specifically: {e}")
                continue
                    
        if not results:
            raise ValueError(f"No valid prices found in yfinance response for {tickers}")
            
        return results

    @agent_trace("DataService.get_bid_ask")
    async def get_bid_ask(self, ticker: str) -> tuple[float, float]:
        """Fetches the actual real-time bid and ask for slippage calculation via yfinance."""
        try:
            def fetch():
                info = yf.Ticker(ticker).info
                bid = info.get('bid', 0.0)
                ask = info.get('ask', 0.0)
                # Fallback to currentPrice if bid/ask is missing (e.g. after hours)
                if bid == 0.0 or ask == 0.0:
                    current = info.get('currentPrice', info.get('previousClose', 1.0))
                    return current, current 
                return bid, ask
            return await asyncio.to_thread(fetch)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to fetch Bid/Ask for {ticker}: {e}")
            return 0.0, 0.0

    @agent_trace("DataService.stream_realtime_data")
    async def stream_realtime_data(self, tickers: List[str]):
        """
        Connects to Polygon WebSocket to stream real-time prices into Redis.
        """
        loop = asyncio.get_running_loop()
        def handle_msg(msgs):
            for m in msgs:
                # Trade event (T) or Quote event (Q)
                if hasattr(m, 'price'):
                    # Bug M-04: Ensure async Redis write is scheduled
                    asyncio.run_coroutine_threadsafe(redis_service.set_price(m.symbol, m.price), loop)
                elif hasattr(m, 'bid_price'):
                    # Mid-price approximation
                    mid = (m.bid_price + m.ask_price) / 2
                    asyncio.run_coroutine_threadsafe(redis_service.set_price(m.symbol, mid), loop)

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
