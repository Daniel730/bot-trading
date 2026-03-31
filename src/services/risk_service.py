import numpy as np
from typing import List, Dict
from src.config import settings

class RiskService:
    @staticmethod
    def calculate_kelly_size(confidence_score: float, win_loss_ratio: float = 1.0) -> float:
        """
        Calculates position size using Fractional Kelly Criterion.
        f* = p - (1-p)/b
        """
        p = confidence_score
        b = win_loss_ratio
        if b == 0: return 0
        
        kelly_f = p - (1 - p) / b
        # Apply fractional Kelly and limit by max risk per trade
        suggested_size = max(0, kelly_f * settings.KELLY_FRACTION)
        return min(suggested_size, settings.MAX_RISK_PER_TRADE)

    @staticmethod
    def monte_carlo_var(returns: np.ndarray, confidence_level: float = 0.95, simulations: int = 10000) -> float:
        """
        Calculates Value at Risk using Monte Carlo simulation.
        """
        if len(returns) < 2: return 0.0
        
        mu = np.mean(returns)
        sigma = np.std(returns)
        
        sim_returns = np.random.normal(mu, sigma, simulations)
        var = np.percentile(sim_returns, (1 - confidence_level) * 100)
        return abs(var)

risk_service = RiskService()
