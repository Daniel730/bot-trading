import pandas as pd
import numpy as np
import logging
import time
from typing import Dict, Any
from src.services.data_service import data_service
from src.services.volatility_service import volatility_service
from src.services.persistence_service import persistence_service, MarketRegime
from src.config import settings

logger = logging.getLogger(__name__)

class MarketRegimeService:
    def __init__(self, window: int = 20, cache_ttl_seconds: float | None = None):
        self.window = window
        self.cache_ttl_seconds = (
            float(cache_ttl_seconds)
            if cache_ttl_seconds is not None
            else float(settings.SCAN_INTERVAL_SECONDS)
        )
        self._regime_cache: dict[str, tuple[float, Dict[str, Any]]] = {}

    def _copy_regime_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "regime": result["regime"],
            "confidence": result["confidence"],
            "features": dict(result.get("features") or {}),
        }

    async def classify_current_regime(self, ticker: str = "SPY") -> Dict[str, Any]:
        """
        Classifies the current market regime for a specific ticker (default SPY).
        Returns regime type and features.
        """
        try:
            cache_key = ticker.upper()
            if self.cache_ttl_seconds > 0:
                cached = self._regime_cache.get(cache_key)
                if cached and time.monotonic() - cached[0] <= self.cache_ttl_seconds:
                    return self._copy_regime_result(cached[1])

            # 1. Fetch historical data (daily for regime detection)
            hist = data_service.get_historical_data([ticker], period="60d", interval="1d")
            if hist.empty:
                return {
                    "regime": MarketRegime.STABLE,
                    "confidence": settings.MARKET_REGIME_FALLBACK_CONFIDENCE,
                    "features": {},
                }

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
                return {
                    "regime": MarketRegime.STABLE,
                    "confidence": settings.MARKET_REGIME_FALLBACK_CONFIDENCE,
                    "features": {},
                }

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
            confidence = settings.MARKET_REGIME_BASE_CONFIDENCE

            # Trending logic
            if curr_ema_s > curr_ema_l * settings.MARKET_REGIME_EMA_BULL_FACTOR and current_price > curr_ema_s:
                regime = MarketRegime.TRENDING_UP
            elif curr_ema_s < curr_ema_l * settings.MARKET_REGIME_EMA_BEAR_FACTOR and current_price < curr_ema_s:
                regime = MarketRegime.TRENDING_DOWN

            # Volatility Overrides
            # High volatility if daily returns std > certain threshold OR L2 entropy is very high
            if volatility > settings.MARKET_REGIME_VOLATILITY_HIGH or entropy > settings.MARKET_REGIME_ENTROPY_SPIKE:
                regime = MarketRegime.VOLATILE
            elif volatility < settings.MARKET_REGIME_VOLATILITY_LOW:
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
            result = {
                "regime": regime,
                "confidence": confidence,
                "features": features
            }
            await persistence_service.log_market_regime(result)

            if self.cache_ttl_seconds > 0:
                self._regime_cache[cache_key] = (
                    time.monotonic(),
                    self._copy_regime_result(result),
                )

            return result

        except Exception as e:
            logger.error(f"Error classifying market regime: {e}")
            return {
                "regime": MarketRegime.STABLE,
                "confidence": settings.MARKET_REGIME_FALLBACK_CONFIDENCE,
                "features": {},
            }

market_regime_service = MarketRegimeService()
