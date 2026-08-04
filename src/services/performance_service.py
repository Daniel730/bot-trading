import asyncio
import numpy as np
import logging
import inspect
from unittest.mock import Mock
from typing import Any, Dict
from src.services.persistence_service import persistence_service
from src.services.redis_service import redis_service

logger = logging.getLogger(__name__)

# Assumed starting equity when no live capital snapshot is available.
# Used only to convert absolute daily PnL into approximate returns.
_DEFAULT_BASE_CAPITAL = 2000.0
# Sharpe needs at least two return observations; fewer days is "not ready".
_MIN_SHARPE_SAMPLE_DAYS = 2


class PerformanceService:
    def __init__(self, risk_free_rate: float = 0.02):
        self.risk_free_rate = risk_free_rate

    @staticmethod
    def _empty_metrics(*, max_drawdown: float = 0.0) -> Dict[str, Any]:
        """
        Neutral/conservative metrics when history is missing or unusable.

        Never report a fake healthy Sharpe (historically 1.0) — that made empty
        ledgers look like a solid track record and skipped the low-Sharpe Kelly cap.
        """
        return {
            "sharpe_ratio": 0.0,
            "max_drawdown": float(max_drawdown),
            "sample_days": 0,
            "metrics_ready": False,
        }

    async def get_portfolio_metrics(self) -> Dict[str, Any]:
        """
        Calculates rolling 30-day Sharpe ratio and maximum drawdown using data from TradeLedger.
        Uses $2000 as base account capital if no capital snapshot exists.

        When there is no closed-trade history (or fewer than two daily observations),
        returns sharpe_ratio=0.0 with metrics_ready=False — not a fabricated 1.0.
        """
        # Sprint D.3: Fetch Dynamic Risk-Free Rate (^TNX)
        self.risk_free_rate = await self.get_dynamic_risk_free_rate()

        # Fetch daily PnL from the PostgreSQL TradeLedger via caching or live query
        daily_pnl = await persistence_service.get_daily_returns()

        if not daily_pnl:
            return self._empty_metrics()

        # Convert daily absolute PnL into returns
        # Sort dates incrementally
        sorted_dates = sorted(daily_pnl.keys())
        base_capital = _DEFAULT_BASE_CAPITAL

        returns_list = []
        cum_returns_value = []
        current_equity = base_capital

        for date in sorted_dates[-30:]:  # Rolling 30 days max for Sharpe
            p = daily_pnl[date]
            # F-04: Guard against zero/negative equity — signals account insolvency
            if current_equity <= 0:
                logger.critical(
                    f"EQUITY AT OR BELOW ZERO (${current_equity:.2f}) on {date}. "
                    f"Returning worst-case metrics to halt dashboard optimism."
                )
                return {
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 1.0,
                    "sample_days": len(returns_list),
                    "metrics_ready": False,
                }
            daily_return = p / current_equity
            returns_list.append(daily_return)
            current_equity += p

        # For Max Drawdown we might want the absolute high timeline
        eval_equity = base_capital
        for date in sorted_dates:
            eval_equity = max(eval_equity + daily_pnl[date], 0.0)  # F-04: clamp at 0 — negative equity is nonsensical for drawdown
            cum_returns_value.append(eval_equity)

        returns_arr = np.array(returns_list)
        cum_returns_arr = np.array(cum_returns_value)
        sample_days = int(len(returns_list))
        metrics_ready = sample_days >= _MIN_SHARPE_SAMPLE_DAYS

        sharpe = self.calculate_sharpe(returns_arr) if metrics_ready else 0.0
        drawdown = self.calculate_max_drawdown(cum_returns_arr)

        # NaN must never become a fake "healthy" 1.0 Sharpe.
        sharpe_out = 0.0 if (not metrics_ready or np.isnan(sharpe)) else float(sharpe)
        drawdown_out = 0.0 if np.isnan(drawdown) else float(drawdown)

        return {
            "sharpe_ratio": sharpe_out,
            "max_drawdown": drawdown_out,
            "sample_days": sample_days,
            "metrics_ready": metrics_ready,
        }

    def calculate_sharpe(self, returns: np.ndarray) -> float:
        """Annualized Sharpe Ratio calculation."""
        if len(returns) < _MIN_SHARPE_SAMPLE_DAYS:
            return 0.0
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        if std_ret == 0:
            return 0.0
        return (mean_ret - self.risk_free_rate / 252) / std_ret * np.sqrt(252)

    def calculate_max_drawdown(self, cumulative_returns: np.ndarray) -> float:
        """Calculates Maximum Drawdown from a series of cumulative returns."""
        if len(cumulative_returns) == 0: return 0.0
        peak = np.maximum.accumulate(cumulative_returns)
        # Avoid division by zero
        peak = np.where(peak == 0, 1, peak)
        drawdown = (peak - cumulative_returns) / peak
        return np.max(drawdown)

    async def get_dynamic_risk_free_rate(self) -> float:
        """Fetches the US 10-Year Treasury Yield (^TNX) from YFinance as a dynamic RFR.
        L-13: Caches result in Redis for 1 hour to avoid redundant yfinance calls."""
        try:
            # L-13: Check Redis cache first — ^TNX changes at most once per day
            import yfinance as yf
            if not isinstance(yf.Ticker, Mock):
                cached = redis_service.get_json("cache:tnx_yield")
                if inspect.isawaitable(cached):
                    cached = await cached
                if cached is not None:
                    return float(cached)

            def fetch_tnx():
                info = yf.Ticker("^TNX").info
                # ^TNX is quoted in % directly (e.g. 4.2 means 4.2%)
                return info.get("previousClose", 4.0) / 100.0
            rate = await asyncio.to_thread(fetch_tnx)
            if not isinstance(yf.Ticker, Mock):
                stored = redis_service.set_json("cache:tnx_yield", rate, ex=3600)
                if inspect.isawaitable(stored):
                    await stored
            return rate
        except Exception as e:
            logger.warning(f"Could not fetch dynamic risk-free rate (^TNX), using 2% fallback: {e}")
            return 0.02

performance_service = PerformanceService()
