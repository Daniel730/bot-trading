import pandas as pd
import numpy as np
import logging
from typing import Dict, Any
from src.services.data_service import data_service
from src.services.volatility_service import volatility_service
from src.services.persistence_service import persistence_service, MarketRegime

logger = logging.getLogger(__name__)

class MarketRegimeService:
    def __init__(self, window: int = 20):
        self.window = window

    async def classify_current_regime(self, ticker: str = "SPY") -> Dict[str, Any]:
        """
        Classifies the current market regime for a specific ticker (default SPY).
        Returns regime type and features.
        """
        try:
            # 1. Fetch historical data (daily for regime detection)
            hist = data_service.get_historical_data([ticker], period="60d", interval="1d")
            if hist.empty:
                return {"regime": MarketRegime.STABLE, "confidence": 0.5, "features": {}}

            # 2. Calculate Indicators
            # P-06 (2026-04-26): yfinance returns a 1-column DataFrame when a
            # single-element ticker list is passed. df.iloc[-1] is then a
            # Series, and float(Series) blows up with
            #   "float() argument must be a string or a real number, not 'Series'"
            # Coerce to a 1-D Series so all downstream scalar conversions work.
            prices = hist
            if isinstance(prices, pd.DataFrame):
                if prices.shape[1] == 1:
                    prices = prices.iloc[:, 0]
                else:
                    # Multiple tickers were returned — pick the requested one
                    # if present, otherwise the first column.
                    prices = prices[ticker] if ticker in prices.columns else prices.iloc[:, 0]
            prices = prices.dropna()
            if prices.empty:
                return {"regime": MarketRegime.STABLE, "confidence": 0.5, "features": {}}

            returns = prices.pct_change().dropna()

            # Volatility (ATR-like approach using Std)
            volatility = float(returns.std()) * np.sqrt(252)

            # Trend (EMA 20/50 Crossover or Price vs EMA)
            ema_short = prices.ewm(span=10).mean()
            ema_long = prices.ewm(span=50).mean()

            current_price = float(prices.iloc[-1])
            curr_ema_s = float(ema_short.iloc[-1])
            curr_ema_l = float(ema_long.iloc[-1])

            # L2 Entropy for real-time micro-regime
            entropy = await volatility_service.get_l2_entropy(ticker)

            # 3. Decision Logic
            regime = MarketRegime.STABLE
            confidence = 0.7

            # Trending logic
            if curr_ema_s > curr_ema_l * 1.01 and current_price > curr_ema_s:
                regime = MarketRegime.TRENDING_UP
            elif curr_ema_s < curr_ema_l * 0.99 and current_price < curr_ema_s:
                regime = MarketRegime.TRENDING_DOWN

            # Volatility Overrides
            # High volatility if daily returns std > certain threshold OR L2 entropy is very high
            if volatility > 0.30 or entropy > 0.85:
                regime = MarketRegime.VOLATILE
            elif volatility < 0.10:
                # If neither trending nor volatile, it's sideways/stable
                if regime not in [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]:
                    regime = MarketRegime.SIDEWAYS

            features = {
                "volatility_annualized": float(volatility),
                "l2_entropy": float(entropy),
                "ema_spread": float((curr_ema_s - curr_ema_l) / curr_ema_l),
                "price_relative_ema": float((current_price - curr_ema_s) / curr_ema_s)
            }

            # 4. Log to DB
            await persistence_service.log_market_regime({
                "regime": regime,
                "confidence": confidence,
                "features": features
            })

            return {
                "regime": regime,
                "confidence": confidence,
                "features": features
            }

        except Exception as e:
            logger.error(f"Error classifying market regime: {e}")
            return {"regime": MarketRegime.STABLE, "confidence": 0.5, "features": {}}

market_regime_service = MarketRegimeService()
