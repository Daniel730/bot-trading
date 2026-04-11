import numpy as np
import logging
from typing import Dict
from src.services.persistence_service import persistence_service

logger = logging.getLogger(__name__)

class PerformanceService:
    def __init__(self, risk_free_rate: float = 0.02):
        self.risk_free_rate = risk_free_rate

    async def get_portfolio_metrics(self) -> Dict[str, float]:
        """
        Calculates rolling 30-day Sharpe ratio and maximum drawdown using data from TradeLedger.
        Uses $2000 as base account capital if no capital snapshot exists.
        """
        # Sprint D.3: Fetch Dynamic Risk-Free Rate (^TNX)
        self.risk_free_rate = await self.get_dynamic_risk_free_rate()
        
        # Fetch daily PnL from the PostgreSQL TradeLedger via caching or live query
        daily_pnl = await persistence_service.get_daily_returns()
        
        if not daily_pnl:
            return {"sharpe_ratio": 1.0, "max_drawdown": 0.0}
            
        # Convert daily absolute PnL into returns
        # Sort dates incrementally
        sorted_dates = sorted(daily_pnl.keys())
        base_capital = 2000.0
        
        returns_list = []
        cum_returns_value = []
        current_equity = base_capital
        
        for date in sorted_dates[-30:]:  # Rolling 30 days max for Sharpe
            p = daily_pnl[date]
            daily_return = p / current_equity if current_equity > 0 else 0
            returns_list.append(daily_return)
            current_equity += p
            
        # For Max Drawdown we might want the absolute high timeline
        eval_equity = base_capital
        for date in sorted_dates:
            eval_equity += daily_pnl[date]
            cum_returns_value.append(eval_equity)
            
        returns_arr = np.array(returns_list)
        cum_returns_arr = np.array(cum_returns_value)
        
        sharpe = self.calculate_sharpe(returns_arr)
        drawdown = self.calculate_max_drawdown(cum_returns_arr)
        
        return {
            "sharpe_ratio": float(sharpe) if not np.isnan(sharpe) else 1.0,
            "max_drawdown": float(drawdown) if not np.isnan(drawdown) else 0.0
        }

    def calculate_sharpe(self, returns: np.ndarray) -> float:
        """Annualized Sharpe Ratio calculation."""
        if len(returns) < 2: return 0.0
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        if std_ret == 0: return 0.0
        return (mean_ret - self.risk_free_rate/252) / std_ret * np.sqrt(252)

    def calculate_max_drawdown(self, cumulative_returns: np.ndarray) -> float:
        """Calculates Maximum Drawdown from a series of cumulative returns."""
        if len(cumulative_returns) == 0: return 0.0
        peak = np.maximum.accumulate(cumulative_returns)
        # Avoid division by zero
        peak = np.where(peak == 0, 1, peak)
        drawdown = (peak - cumulative_returns) / peak
        return np.max(drawdown)

    async def get_dynamic_risk_free_rate(self) -> float:
        """Fetches the US 10-Year Treasury Yield (^TNX) from YFinance as a dynamic RFR."""
        try:
            import yfinance as yf
            import asyncio
            def fetch_tnx():
                info = yf.Ticker("^TNX").info
                # ^TNX is quoted in % directly (e.g. 4.2 means 4.2%)
                return info.get("previousClose", 4.0) / 100.0
            return await asyncio.to_thread(fetch_tnx)
        except Exception as e:
            logger.warning(f"Could not fetch dynamic risk-free rate (^TNX), using 2% fallback: {e}")
            return 0.02

performance_service = PerformanceService()
