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

    @staticmethod
    def check_cluster_exposure(sector: str, active_portfolio: List[Dict]) -> Dict:
        """
        Calculates current exposure for a sector and returns a status dict.
        :param sector: The sector to check.
        :param active_portfolio: List of active trades with their 'size' and 'sector'.
        """
        total_portfolio_value = sum(trade.get('size', 0) for trade in active_portfolio)
        if total_portfolio_value == 0:
            return {"exposure_pct": 0.0, "allowed": True}
            
        sector_value = sum(trade.get('size', 0) for trade in active_portfolio if trade.get('sector') == sector)
        exposure_pct = sector_value / total_portfolio_value
        
        allowed = exposure_pct < settings.MAX_SECTOR_EXPOSURE
        
        return {
            "exposure_pct": exposure_pct,
            "allowed": allowed,
            "current_sector_value": sector_value,
            "total_portfolio_value": total_portfolio_value
        }

    @staticmethod
    def get_all_sector_exposures(active_portfolio: List[Dict]) -> Dict[str, float]:
        """
        Returns a map of sector name -> exposure percentage.
        """
        total_value = sum(trade.get('size', 0) for trade in active_portfolio)
        if total_value == 0:
            return {}
            
        exposures = {}
        sectors = set(trade.get('sector', 'Unknown') for trade in active_portfolio)
        for sector in sectors:
            sector_value = sum(trade.get('size', 0) for trade in active_portfolio if trade.get('sector') == sector)
            exposures[sector] = sector_value / total_value
            
        return exposures

risk_service = RiskService()
