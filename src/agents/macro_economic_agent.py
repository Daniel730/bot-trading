import logging
import pandas as pd
from typing import Dict, Literal
from src.services.data_service import DataService

class MacroEconomicAgent:
    def __init__(self, rate_threshold: float = 0.05, inflation_threshold: float = 0.04):
        """
        Initialize the MacroEconomicAgent with macro thresholds and auxiliary services.
        
        Parameters:
            rate_threshold (float): Interest rate threshold used to classify market risk; when current interest rate is greater than this value it contributes to a "RISK_OFF" decision.
            inflation_threshold (float): Inflation threshold used to classify market risk; when current inflation is greater than this value it contributes to a "RISK_OFF" decision.
        
        Notes:
            This sets instance attributes `rate_threshold`, `inflation_threshold`, `data_service` (a DataService instance), and `logger`.
        """
        self.rate_threshold = rate_threshold
        self.inflation_threshold = inflation_threshold
        self.data_service = DataService()
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _extract_series(df: pd.DataFrame, ticker: str) -> pd.Series:
        """
        Return a 1-D pandas Series of close prices for the requested ticker.
        
        The function returns a cleaned, one-dimensional price series (NaNs removed) using the first applicable source from the input:
        - If `df` is already a `pd.Series`, that series with NaNs dropped is returned.
        - If `df` is not a non-empty `pd.DataFrame`, an empty float `pd.Series` is returned.
        - If `ticker` is a column in `df`, that column with NaNs dropped is returned.
        - If a `"Close"` column exists and is a `pd.Series`, it is returned with NaNs dropped.
        - If `df` contains exactly one column, that column with NaNs dropped is returned.
        - Otherwise an empty float `pd.Series` is returned.
        
        Parameters:
            df (pd.DataFrame | pd.Series): Input price data or a single-series time series.
            ticker (str): Column name to prefer when extracting the close-price series.
        
        Returns:
            pd.Series: A one-dimensional series of numeric close prices with missing values removed, or an empty float series if no usable data is found.
        """
        if isinstance(df, pd.Series):
            return df.dropna()

        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.Series(dtype="float64")

        # Most callers receive a single-column frame for one ticker.
        if ticker in df.columns:
            return df[ticker].dropna()
        if "Close" in df.columns:
            close_series = df["Close"]
            if isinstance(close_series, pd.Series):
                return close_series.dropna()
        if len(df.columns) == 1:
            return df.iloc[:, 0].dropna()
        return pd.Series(dtype="float64")

    def analyze_market_state(self, interest_rate: float, inflation: float) -> str:
        """
        Determine whether the market is in a "RISK_ON" or "RISK_OFF" state based on macro thresholds.
        
        Returns:
            str: `"RISK_OFF"` if `interest_rate` is greater than `self.rate_threshold` or `inflation` is greater than `self.inflation_threshold`, `"RISK_ON"` otherwise.
        """
        if interest_rate > self.rate_threshold or inflation > self.inflation_threshold:
            self.logger.info(f"Macro state: RISK_OFF (Rates: {interest_rate}, Inflation: {inflation})")
            return "RISK_OFF"
        
        self.logger.info(f"Macro state: RISK_ON (Rates: {interest_rate}, Inflation: {inflation})")
        return "RISK_ON"

    async def get_ticker_regime(self, ticker: str) -> Literal["BULLISH", "BEARISH", "EXTREME_VOLATILITY"]:
        """
        Determine the market regime for a ticker using recent price history.
        
        Uses a flash-crash circuit breaker and moving-average trend to classify the regime:
        - If the most recent daily drop is greater than 3%, returns "EXTREME_VOLATILITY".
        - Otherwise compares 20-day and 50-day simple moving averages: returns "BULLISH" when SMA20 > SMA50, "BEARISH" otherwise.
        If there is insufficient data for SMA50, returns "BULLISH". If the price series has fewer than two points or an error occurs, returns "BEARISH".
        
        Returns:
            str: One of `"BULLISH"`, `"BEARISH"`, or `"EXTREME_VOLATILITY"`.
        """
        try:
            # Fetch 60d to ensure we have enough for SMA 50
            df = await self.data_service.get_historical_data_async([ticker], "60d", "1d")
            series = self._extract_series(df, ticker)
            if len(series) < 2:
                self.logger.warning(f"Not enough data to infer regime for {ticker}. Defaulting to BEARISH.")
                return "BEARISH"
            
            # 1. Check for Flash Crash (Circuit Breaker)
            last_close = series.iloc[-1]
            prev_close = series.iloc[-2]
            daily_change = (last_close - prev_close) / prev_close
            
            if daily_change < -0.03:
                self.logger.warning(f"CIRCUIT BREAKER: {ticker} panic detected ({daily_change*100:.2f}%)")
                return "EXTREME_VOLATILITY"

            # 2. Institutional Trend (SMA 20/50)
            sma20 = series.rolling(window=20).mean().iloc[-1]
            sma50 = series.rolling(window=50).mean().iloc[-1]
            
            if pd.isna(sma50):
                self.logger.warning(f"Not enough data for SMA50 on {ticker}. Defaulting to BULLISH.")
                return "BULLISH"

            regime = "BULLISH" if sma20 > sma50 else "BEARISH"
            self.logger.info(f"Regime for {ticker}: {regime} (SMA20: {sma20:.2f}, SMA50: {sma50:.2f})")
            return regime
        except Exception as e:
            self.logger.error(f"Error calculating regime for {ticker}: {e}")
            return "BEARISH" # Safe default

    async def fetch_current_indicators(self) -> dict:
        """
        Fetches latest macro data from external sources (e.g., ^TNX).
        Placeholder implementation.
        """
        return {
            "interest_rate": 0.042,
            "inflation": 0.031
        }

    async def get_macro_summary(self) -> dict:
        from src.services.data_service import data_service

        prices = await data_service.get_latest_price_async(["^TNX", "^VIX", "SPY", "QQQ"])
        hist = await data_service.get_historical_data_async(["SPY"], "200d", "1d")
        if isinstance(hist, pd.DataFrame) and "Close" in hist.columns:
            spy_50d = float(hist["Close"].tail(50).mean())
        elif hasattr(hist, "tail"):
            spy_50d = float(hist.tail(50).mean())
        else:
            spy_50d = float(prices.get("SPY", 0.0))
        spy_curr = float(prices.get("SPY", 0.0))
        market_trend = "Bullish" if spy_curr >= spy_50d else "Bearish"
        return {
            "yield_10y": float(prices.get("^TNX", 0.0)),
            "vix": float(prices.get("^VIX", 0.0)),
            "market_trend": market_trend,
            "spy_curr": spy_curr,
            "spy_50d": spy_50d,
            "risk_on": market_trend == "Bullish" and float(prices.get("^VIX", 0.0)) < 25.0,
        }

    def format_summary_for_telegram(self, summary: dict) -> str:
        risk_text = "🟢 RISK-ON" if summary.get("risk_on") else "🔴 RISK-OFF"
        return (
            "🌐 **Macro Economic Summary**\n\n"
            f"{risk_text}\n"
            f"10Y Yield: {float(summary.get('yield_10y', 0.0)):.2f}%\n"
            f"VIX: {float(summary.get('vix', 0.0)):.2f}\n"
            f"Market Trend: {summary.get('market_trend', 'Unknown')}"
        )

macro_economic_agent = MacroEconomicAgent()
