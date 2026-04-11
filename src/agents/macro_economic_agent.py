import logging
import asyncio
import pandas as pd
from typing import Dict, Literal
from src.services.data_service import DataService

class MacroEconomicAgent:
    def __init__(self, rate_threshold: float = 0.05, inflation_threshold: float = 0.04):
        self.rate_threshold = rate_threshold
        self.inflation_threshold = inflation_threshold
        self.data_service = DataService()
        self.logger = logging.getLogger(__name__)

    def analyze_market_state(self, interest_rate: float, inflation: float) -> str:
        """
        Determines if the market is RISK_ON or RISK_OFF based on macro indicators.
        """
        if interest_rate > self.rate_threshold or inflation > self.inflation_threshold:
            self.logger.info(f"Macro state: RISK_OFF (Rates: {interest_rate}, Inflation: {inflation})")
            return "RISK_OFF"
        
        self.logger.info(f"Macro state: RISK_ON (Rates: {interest_rate}, Inflation: {inflation})")
        return "RISK_ON"

    async def get_ticker_regime(self, ticker: str) -> Literal["BULLISH", "BEARISH", "EXTREME_VOLATILITY"]:
        """
        Determines the regime of a beacon asset.
        Logic: BULLISH if SMA20 > SMA50, BEARISH if SMA20 < SMA50.
        Circuit Breaker: EXTREME_VOLATILITY if daily drop > 3%.
        """
        try:
            # Fetch 60d to ensure we have enough for SMA 50
            df = await asyncio.to_thread(self.data_service.get_historical_data, [ticker], "60d", "1d")
            if isinstance(df, pd.Series):
                df = df.to_frame(name=ticker)
                
            series = df[ticker]
            
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

macro_economic_agent = MacroEconomicAgent()
