import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, time as dtime
import pytz
import logging
import holidays
from polygon import RESTClient
from src.config import POLYGON_API_KEY
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class DataService:
    def __init__(self):
        self.client = RESTClient(api_key=POLYGON_API_KEY)
        self.ny_tz = pytz.timezone("America/New_York")
        self.wet_tz = pytz.timezone("WET")
        self.us_holidays = holidays.US()

    def get_historical_data(self, ticker: str, period: str = "90d") -> pd.DataFrame:
        """
        Fetches historical daily data from yfinance.
        """
        ticker_data = yf.Ticker(ticker)
        df = ticker_data.history(period=period)
        return df

    def get_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetches current snapshot prices from Polygon.io.
        """
        try:
            # Using RESTClient snapshot for multiple tickers
            # This is more efficient than individual calls for a small number of tickers.
            snapshot = self.client.get_snapshot_all(
                market_type="stocks",
                tickers=",".join(tickers)
            )
            
            prices = {}
            for ticker_info in snapshot:
                ticker = ticker_info.ticker
                price = ticker_info.last_trade.price if ticker_info.last_trade else ticker_info.day.close
                if price:
                    prices[ticker] = float(price)
            return prices
        except Exception as e:
            logger.warning(f"Polygon Snapshot failed: {e}. Falling back to yfinance.")
            # Fallback to yfinance if Polygon fails
            prices = {}
            for ticker in tickers:
                t = yf.Ticker(ticker)
                try:
                    # Using history(1d) as currentPrice might be delayed or unavailable
                    df = t.history(period="1d")
                    if not df.empty:
                        prices[ticker] = float(df['Close'].iloc[-1])
                except Exception as ex:
                    logger.error(f"yfinance fallback failed for {ticker}: {ex}")
            return prices

    def get_news_context(self, tickers: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetches recent news headlines from Polygon.io.
        """
        try:
            news = self.client.list_ticker_news(ticker=",".join(tickers), limit=limit)
            return [vars(n) for n in news]
        except Exception as e:
            logger.error(f"Failed to fetch news from Polygon: {e}")
            return []

    def is_market_open(self) -> bool:
        """
        Checks if the market is open based on NYSE operating hours (14:30 - 21:00 WET).
        Uses 'holidays' library for NYSE holiday support.
        """
        now_wet = datetime.now(self.wet_tz)
        
        # Weekday check (0=Mon, 4=Fri)
        if now_wet.weekday() >= 5:
            return False
            
        # NYSE Holiday Check (NY Time)
        now_ny = datetime.now(self.ny_tz)
        if now_ny.date() in self.us_holidays:
            return False

        # Time window check (14:30 - 21:00 WET)
        start_time = dtime(14, 30)
        end_time = dtime(21, 0)
        current_time = now_wet.time()
        
        return start_time <= current_time <= end_time

    def get_ny_time(self) -> datetime:
        return datetime.now(self.ny_tz)
