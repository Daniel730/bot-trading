from typing import Dict, Optional, Any, List
import numpy as np
from src.services.agent_log_service import agent_trace

class FeeAnalyzer:
    def __init__(self, max_friction_pct: float = 0.015):
        self.max_friction_pct = max_friction_pct

    def check_fees(self, ticker: str, amount_fiat: float, commission: float = 0.0, fx_fee: float = 0.0, spread_est: float = 0.0, flat_spread: float = 0.0) -> Dict:
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

        total_friction = commission + fx_fee + spread_est + flat_spread
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

    async def get_execution_params(self, ticker: str) -> Dict[str, float]:
        """
        Calculates dynamic risk parameters for the Java Execution Engine.
        FR-002: RiskScale = f(Sharpe, MaxDrawdown)
        FR-004: ExecutionServiceClient accepts dynamic max_slippage derived from VolatilitySwitch.
        """
        from src.services.performance_service import performance_service
        from src.services.volatility_service import volatility_service
        
        perf_metrics = await performance_service.get_portfolio_metrics()
        sharpe = perf_metrics.get("sharpe_ratio", 1.0)
        drawdown = perf_metrics.get("max_drawdown", 0.0)
        
        # SC-001: Position size scales linearly with drawdown: 0% at 15% drawdown
        risk_multiplier = 1.0
        if drawdown >= 0.15:
            risk_multiplier = 0.0
        elif drawdown > 0:
            risk_multiplier = max(0.0, 1.0 - (drawdown / 0.15))
            
        # User Story 1 Acceptance 2: Sharpe ratio < 0.5 => Kelly fraction capped at 0.1
        if sharpe < 0.5:
            risk_multiplier = min(risk_multiplier, 0.1)

        # User Story 3: Tighten maxSlippage if Volatility Switch is HIGH
        vol_status = await volatility_service.get_volatility_status(ticker)
        
        # Default slippage 0.1% (0.001)
        # Acceptance Scenario: Reduce from 0.001 to 0.0005 in high vol
        max_slippage = 0.001
        if vol_status == "HIGH_VOLATILITY":
            max_slippage = 0.0005
            
        return {
            "risk_multiplier": risk_multiplier,
            "max_slippage_pct": max_slippage,
            "volatility_status": vol_status
        }

    @agent_trace("RiskService.check_hedging")
    async def check_hedging(self, hedging_state: str = "NORMAL") -> Dict[str, Any]:
        """
        Feature 015/017: Auto-Hedging Protocol (DEFCON 1).
        Architecture Rule 5 (FR-005): Includes regional fallbacks (e.g., EU UCITS).
        Architecture Rule 6 (FR-006): Bypass and alert if no mapping exists.
        """
        if hedging_state == "NORMAL":
            return {"status": "SAFE", "hedges": []}
        
        try:
            from src.config import settings
        except ImportError:
            class DummySettings: REGION = "US"
            settings = DummySettings()
            
        region = getattr(settings, 'REGION', 'US')
        
        # FR-005: Hardcoded UCITS compliance mapping
        hedge_map = {
            "US": {
                "SPY": "SH",
                "QQQ": "PSQ",
                "IWM": "RWM",
                "DIA": "DOG"
            },
            "EU": {
                "SPY": "XSPS.L", # Invesco S&P 500 Inverse UCITS
                "QQQ": "SQQQ.L", # WisdomTree NASDAQ 100 3x Daily Short (Proxy)
                "IWM": "R2SC.L"  # SPDR Russell 2000 US Small Cap UCITS
            }
        }
        
        current_map = hedge_map.get(region, hedge_map["US"])
        from src.services.brokerage_service import brokerage_service
        portfolio = brokerage_service.get_portfolio()
        
        suggested_hedges = []
        for pos in portfolio:
            ticker = pos.get('ticker', '').split('_')[0]
            if ticker in current_map:
                hedge_ticker = current_map[ticker]
                suggested_hedges.append({
                    "target": ticker,
                    "hedge": hedge_ticker,
                    "amount": pos.get('quantity', 0) * pos.get('averagePrice', 0),
                    "region_compliant": region == "EU"
                })
            elif region == "EU":
                # FR-006: Bypass hedge and log critical alert for unmapped assets in EU
                print(f"AGENT_LOGGER: CRITICAL - EU Compliance Mapping missing for {ticker}. Hedge bypassed.")
        
        return {
            "status": "DEFCON_1",
            "region": region,
            "hedges": suggested_hedges,
            "action": "AUTO_HEDGE_PROPOSED"
        }

    def calculate_friction(self, amount: float, ticker: str = "GENERIC", flat_spread: float = 0.5) -> Dict:
        """
        T007/FR-007: Calculates friction and enforces strict micro-budget rejection.
        If trade < $5.00 and friction > 1.5%, status MUST be FRICTION_REJECT.
        """
        res = self.fee_analyzer.check_fees(ticker=ticker, amount_fiat=amount, flat_spread=flat_spread)
        
        status = "ACCEPTED"
        # Decision 4 / FR-007: Micro-budget threshold check
        if amount < 5.00 and not res["is_acceptable"]:
            status = "FRICTION_REJECT"
            
        return {
            "status": status,
            "is_acceptable": res["is_acceptable"] if status == "ACCEPTED" else False,
            "friction_pct": res["total_friction_percent"],
            "rejection_reason": res["rejection_reason"]
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
