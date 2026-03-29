import yfinance as yf
import pandas as pd
from typing import Dict, Optional, Tuple
from src.models.arbitrage_models import DataServiceError
from tenacity import retry, stop_after_attempt, wait_fixed

class DataService:
    def __init__(self):
        pass

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def fetch_current_prices(self, tickers: list[str]) -> Dict[str, float]:
        """Fetch real-time prices for a list of tickers using yfinance."""
        try:
            data = yf.download(tickers, period="1d", interval="1m", progress=False)
            if data.empty:
                raise DataServiceError(f"No price data found for {tickers}")
            
            prices = {}
            for ticker in tickers:
                # Handle single vs multi-ticker download (pandas column structure)
                if len(tickers) == 1:
                    price = data['Close'].iloc[-1]
                else:
                    price = data['Close'][ticker].iloc[-1]
                prices[ticker] = float(price)
            return prices
        except Exception as e:
            raise DataServiceError(f"Error fetching prices: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def fetch_historical_data(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.Series:
        """Fetch historical close prices for a ticker."""
        try:
            data = yf.download(ticker, period=period, interval=interval, progress=False)
            if data.empty:
                raise DataServiceError(f"No historical data for {ticker}")
            return data['Close']
        except Exception as e:
            raise DataServiceError(f"Error fetching historical data for {ticker}: {e}")

    def get_latest_price(self, ticker: str) -> float:
        """Helper to get a single latest price."""
        return self.fetch_current_prices([ticker])[ticker]
