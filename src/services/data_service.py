import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, time as dtime
import pytz
import logging
from src.config import POLYGON_API_KEY
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class DataService:
    def __init__(self):
        self.polygon_base_url = "https://api.polygon.io"
        self.api_key = POLYGON_API_KEY
        self.ny_tz = pytz.timezone("America/New_York")
        self.wet_tz = pytz.timezone("WET")

    def get_historical_data(self, ticker: str, period: str = "90d") -> pd.DataFrame:
        """
        Fetches historical daily data from yfinance.
        """
        ticker_data = yf.Ticker(ticker)
        df = ticker_data.history(period=period)
        return df

    def get_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetches near real-time snapshot prices from Polygon.io.
        """
        # Note: Polygon snapshot returns for ALL tickers.
        # Filtering for the tickers we care about.
        endpoint = f"{self.polygon_base_url}/v2/snapshot/locale/us/markets/stocks/tickers"
        params = {
            "tickers": ",".join(tickers),
            "apiKey": self.api_key
        }
        
        response = requests.get(endpoint, params=params)
        
        if response.status_code == 200:
            data = response.json()
            prices = {}
            for ticker_info in data.get("tickers", []):
                ticker = ticker_info.get("ticker")
                price = ticker_info.get("lastTrade", {}).get("p")
                if price:
                    prices[ticker] = price
            return prices
        else:
            # Fallback to yfinance if Polygon fails
            prices = {}
            for ticker in tickers:
                t = yf.Ticker(ticker)
                # fast_info is deprecated, use t.info['currentPrice'] or history
                try:
                    prices[ticker] = t.info['currentPrice']
                except:
                    df = t.history(period="1d")
                    if not df.empty:
                        prices[ticker] = df['Close'].iloc[-1]
            return prices

    def get_news_context(self, tickers: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetches recent news headlines from Polygon.io.
        """
        endpoint = f"{self.polygon_base_url}/v2/reference/news"
        params = {
            "ticker.any_of": ",".join(tickers),
            "limit": limit,
            "apiKey": self.api_key
        }
        
        response = requests.get(endpoint, params=params)
        
        if response.status_code == 200:
            return response.json().get("results", [])
        else:
            logger.error(f"Failed to fetch news from Polygon: {response.text}")
            return []

    def is_market_open(self) -> bool:
        """
        Checks if the market is open based on NYSE operating hours (14:30 - 21:00 WET).
        Enforces Principle I and includes basic holiday checks for 2026.
        """
        now_wet = datetime.now(self.wet_tz)
        
        # Check if it's a weekday (0=Mon, 4=Fri)
        if now_wet.weekday() >= 5:
            return False
            
        # NYSE 2026 Holidays (Partial List)
        holidays_2026 = [
            "2026-01-01", # New Year's Day
            "2026-01-19", # Martin Luther King Jr. Day
            "2026-02-16", # Presidents' Day
            "2026-04-03", # Good Friday
            "2026-05-25", # Memorial Day
            "2026-06-19", # Juneteenth
            "2026-07-03", # Independence Day (Observed)
            "2026-09-07", # Labor Day
            "2026-11-26", # Thanksgiving Day
            "2026-12-25", # Christmas Day
        ]
        
        if now_wet.strftime("%Y-%m-%d") in holidays_2026:
            return False

        # Check time window (14:30 - 21:00 WET)
        start_time = dtime(14, 30)
        end_time = dtime(21, 0)
        current_time = now_wet.time()
        
        return start_time <= current_time <= end_time

    def get_ny_time(self) -> datetime:
        return datetime.now(self.ny_tz)
