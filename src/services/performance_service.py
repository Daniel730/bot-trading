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
        Calculates rolling 30-day Sharpe ratio and maximum drawdown.
        Currently uses a baseline for simulation until full ledger historicals are populated.
        """
        # FR-001: System MUST track daily portfolio returns, cumulative drawdown, and rolling 30-day Sharpe ratio
        
        # TODO: Implement actual SQL calculation from trade_ledger and portfolio_performance
        # For now, return safe defaults that can be overridden in tests
        return {
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.02
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

performance_service = PerformanceService()
