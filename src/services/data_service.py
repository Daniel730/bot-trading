import yfinance as yf
import pandas as pd
from polygon import RESTClient
from typing import List, Optional
from src.config import settings
import asyncio

class DataService:
    def __init__(self):
        self.polygon_client = RESTClient(api_key=settings.POLYGON_API_KEY)

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

    def get_latest_price(self, tickers: List[str]) -> dict:
        """
        Fetches the latest prices for given tickers using yfinance.
        """
        try:
            # period="1d", interval="1m" to get the very latest
            df = yf.download(tickers, period="1d", interval="1m", progress=False)
            if df.empty:
                return {}
            
            latest = {}
            # Handle multi-index (multiple tickers) or flat (single ticker)
            if len(tickers) > 1:
                # df['Close'] is a DataFrame
                for ticker in tickers:
                    val = df['Close'][ticker].iloc[-1]
                    if not pd.isna(val):
                        latest[ticker] = float(val)
            else:
                ticker = tickers[0]
                val = df['Close'].iloc[-1]
                if not pd.isna(val):
                    latest[ticker] = float(val)
            return latest
        except Exception as e:
            print(f"DEBUG: yfinance error for latest price {tickers}: {e}")
            return {}

    async def stream_realtime_data(self, tickers: List[str], callback):
        """
        Connects to Polygon WebSocket to stream real-time prices.
        Implementation uses Polygon SDK patterns.
        """
        # Note: Actual WebSocket implementation requires an active loop and auth
        print(f"Subscribing to Polygon.io WebSocket for {tickers}...")
        # Placeholder for real-time processing logic
        while True:
            # Simulate receiving data
            await asyncio.sleep(5)
            # callback(simulated_data)

data_service = DataService()
