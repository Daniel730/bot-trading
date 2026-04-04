import numpy as np
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from src.config import settings

logger = logging.getLogger(__name__)

class RiskService:
    def __init__(self):
        self.sector_freezes: Dict[str, datetime] = {} # sector -> expiry_time
        self.HALT_DURATION_MINUTES = 60 # 1 hour freeze on correlated risk

    def calculate_kelly_size(self, confidence_score: float, structural_integrity_score: Optional[int] = None, win_loss_ratio: float = 1.0) -> float:
        """
        Calculates position size using Fractional Kelly Criterion.
        f* = p - (1-p)/b
        Additionally adjusts the final fraction based on the structural integrity score.
        """
        p = confidence_score
        b = win_loss_ratio
        if b == 0: return 0
        
        kelly_f = p - (1 - p) / b
        
        # Apply fractional Kelly
        suggested_size = max(0, kelly_f * settings.KELLY_FRACTION)
        
        # Feature 009: Dynamic Kelly adjustment based on Structural Integrity
        # If integrity is high (e.g., 90+), we take the full suggested size.
        # If integrity is borderline (e.g., 40-50), we reduce the size by up to 50%.
        if structural_integrity_score is not None:
            # Linear scaling from 0.5 (at score 40) to 1.0 (at score 100)
            adjustment = max(0.5, (structural_integrity_score - 40) / 60.0 + 0.5)
            # Ensure adjustment doesn't exceed 1.0
            adjustment = min(1.0, adjustment)
            suggested_size *= adjustment
            logger.info(f"Dynamic Kelly: Integrity {structural_integrity_score} -> Adjustment {adjustment:.2f}")

        # Limit by max risk per trade
        return min(suggested_size, settings.MAX_RISK_PER_TRADE)

    def evaluate_correlated_risks(self, sector: str, ticker_risks: List[Dict]):
        """
        SC-004: Dispara um 'Sector Freeze' se riscos correlacionados forem detetados em 3+ ativos.
        :param ticker_risks: List of dicts with 'ticker' and 'score'.
        """
        low_integrity_count = sum(1 for r in ticker_risks if r['score'] < 50)
        
        if low_integrity_count >= 3:
            rationale = f"Correlated Risk: {low_integrity_count} tickers in sector '{sector}' have integrity score < 50."
            self.trigger_sector_freeze(sector, rationale)
            return True
        return False

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

    def trigger_sector_freeze(self, sector: str, rationale: str):
        """
        Triggers a temporary halt for all trades in a specific sector.
        """
        expiry = datetime.now() + timedelta(minutes=self.HALT_DURATION_MINUTES)
        self.sector_freezes[sector] = expiry
        logger.warning(f"🚨 SECTOR CIRCUIT BREAKER: '{sector}' frozen until {expiry.strftime('%H:%M:%S')}! Rationale: {rationale}")

    def is_sector_frozen(self, sector: str) -> bool:
        """
        Checks if a sector is currently under a freeze.
        """
        if sector not in self.sector_freezes:
            return False
        
        if datetime.now() > self.sector_freezes[sector]:
            del self.sector_freezes[sector]
            return False
            
        return True

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
