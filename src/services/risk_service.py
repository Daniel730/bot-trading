from typing import Dict, Optional, Any, List
import numpy as np
from src.services.agent_log_service import agent_trace

class FeeAnalyzer:
    def __init__(self, max_friction_pct: float = 0.02):
        self.max_friction_pct = max_friction_pct

    def check_fees(self, ticker: str, amount_fiat: float, commission: float = 0.0, fx_fee: float = 0.0, spread_est: float = 0.0) -> Dict:
        """
        Calculates total friction and determines if the trade is acceptable.
        """
        if amount_fiat <= 0:
            return {
                "ticker": ticker,
                "is_acceptable": False,
                "total_friction_percent": 1.0,
                "rejection_reason": "Amount must be greater than zero"
            }

        total_friction = commission + fx_fee + spread_est
        friction_pct = total_friction / amount_fiat
        
        is_acceptable = friction_pct <= self.max_friction_pct
        
        return {
            "ticker": ticker,
            "is_acceptable": is_acceptable,
            "total_friction_percent": friction_pct,
            "rejection_reason": None if is_acceptable else f"Friction {friction_pct:.2%} exceeds limit {self.max_friction_pct:.2%}"
        }

class KellyCalculator:
    def __init__(self, fractional_kelly: float = 0.25):
        self.fractional_kelly = fractional_kelly

    def calculate_size(self, win_prob: float, win_loss_ratio: float) -> float:
        """
        Calculates position size using the Kelly Criterion.
        f* = (p * b - q) / b
        """
        if win_loss_ratio <= 0:
            return 0.0
            
        loss_prob = 1 - win_prob
        kelly_f = (win_prob * win_loss_ratio - loss_prob) / win_loss_ratio
        
        # Apply fractional Kelly and clamp to [0, 1]
        size = max(0.0, kelly_f * self.fractional_kelly)
        return min(size, 1.0)

class RiskService:
    def __init__(self):
        self.fee_analyzer = FeeAnalyzer()
        self.kelly_calculator = KellyCalculator()
        self.inverse_etfs = {
            "SPY": "SH",     # ProShares Short S&P500
            "QQQ": "PSQ",    # ProShares Short QQQ
            "IWM": "RWM",    # ProShares Short Russell2000
            "DIA": "DOG"     # ProShares Short Dow30
        }

    @agent_trace("RiskService.check_hedging")
    async def check_hedging(self, hedging_state: str = "NORMAL") -> Dict[str, Any]:
        """
        Feature 015 (T016): Auto-Hedging Protocol (DEFCON 1).
        If state is DEFCON_1, suggests inverse ETFs for current long exposure.
        """
        if hedging_state == "NORMAL":
            return {"status": "SAFE", "hedges": []}
        
        # In DEFCON_1, we need to hedge.
        # Fetch current long exposure (simplified)
        from src.services.brokerage_service import brokerage_service
        portfolio = brokerage_service.get_portfolio()
        
        suggested_hedges = []
        for pos in portfolio:
            ticker = pos.get('ticker', '').split('_')[0]
            if ticker in self.inverse_etfs:
                hedge_ticker = self.inverse_etfs[ticker]
                suggested_hedges.append({
                    "target": ticker,
                    "hedge": hedge_ticker,
                    "amount": pos.get('quantity', 0) * pos.get('averagePrice', 0)
                })
        
        return {
            "status": "DEFCON_1",
            "hedges": suggested_hedges,
            "action": "AUTO_HEDGE_PROPOSED"
        }

    def validate_trade(self, ticker: str, amount_fiat: float, win_prob: float, win_loss_ratio: float, hedging_state: str = "NORMAL") -> Dict:
        """
        Performs full risk validation for a proposed trade.
        """
        # DEFCON 1 Veto: Reject high-volatility long trades if market risk is extreme
        if hedging_state == "DEFCON_1" and ticker not in self.inverse_etfs.values():
            return {
                "ticker": ticker,
                "is_acceptable": False,
                "rejection_reason": "DEFCON_1: Market risk extreme. Long trades suppressed."
            }

        fee_check = self.fee_analyzer.check_fees(ticker, amount_fiat)
        kelly_fraction = self.kelly_calculator.calculate_size(win_prob, win_loss_ratio)
        
        is_acceptable = fee_check["is_acceptable"] and kelly_fraction > 0
        
        return {
            "ticker": ticker,
            "is_acceptable": is_acceptable,
            "fee_status": fee_check,
            "kelly_fraction": kelly_fraction,
            "final_amount": amount_fiat * kelly_fraction if is_acceptable else 0.0
        }

risk_service = RiskService()

class PortfolioOptimizer:
    def calculate_covariance(self, returns_df):
        """
        Calculates the covariance matrix for a set of asset returns.
        """
        return returns_df.cov()

    def get_sharpe_ratio(self, returns, risk_free_rate=0.02):
        """
        Calculates the Sharpe Ratio.
        """
        mean_return = returns.mean()
        std_dev = returns.std()
        if std_dev == 0:
            return 0.0
        return (mean_return - risk_free_rate) / std_dev
