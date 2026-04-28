from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import inspect
from src.config import settings
from src.services.agent_log_service import agent_trace

class FeeAnalyzer:
    def __init__(self, max_friction_pct: Optional[float] = None):
        self.max_friction_pct = settings.MAX_FRICTION_PCT if max_friction_pct is None else max_friction_pct

    def check_fees(self, ticker: str, amount_fiat: float, commission: float = 0.0, fx_fee: float = 0.0, spread_est: float = 0.0, flat_spread: float = 0.5) -> Dict:
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
    def __init__(self, fractional_kelly: Optional[float] = None):
        self.fractional_kelly = settings.KELLY_FRACTION if fractional_kelly is None else fractional_kelly

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
        self.sector_freezes: Dict[str, datetime] = {}

    async def get_execution_params(self, ticker: str) -> Dict[str, float]:
        """
        Calculates dynamic risk parameters for the Java Execution Engine.
        FR-002: RiskScale = f(Sharpe, MaxDrawdown)
        FR-004: ExecutionServiceClient accepts dynamic max_slippage derived from VolatilitySwitch.
        """
        from src.services.performance_service import performance_service
        from src.services.volatility_service import volatility_service

        perf_metrics = performance_service.get_portfolio_metrics()
        if inspect.isawaitable(perf_metrics):
            perf_metrics = await perf_metrics
        sharpe = perf_metrics.get("sharpe_ratio", 1.0)
        drawdown = perf_metrics.get("max_drawdown", 0.0)
        
        # SC-001: Position size scales linearly with drawdown: 0% at 15% drawdown
        risk_multiplier = 1.0
        if drawdown >= settings.RISK_DRAWDOWN_ZERO_PCT:
            risk_multiplier = 0.0
        elif drawdown > 0:
            risk_multiplier = max(0.0, 1.0 - (drawdown / settings.RISK_DRAWDOWN_ZERO_PCT))
            
        # User Story 1 Acceptance 2: Sharpe ratio < 0.5 => Kelly fraction capped at 0.1
        if sharpe < settings.RISK_SHARPE_FLOOR:
            risk_multiplier = min(risk_multiplier, settings.RISK_MULTIPLIER_CAP_LOW_SHARPE)

        # User Story 3: Tighten maxSlippage if Volatility Switch is HIGH
        vol_status = volatility_service.get_volatility_status(ticker)
        if inspect.isawaitable(vol_status):
            vol_status = await vol_status
        l2_entropy = volatility_service.get_l2_entropy(ticker)
        if inspect.isawaitable(l2_entropy):
            l2_entropy = await l2_entropy
        
        # Default slippage 0.1% (0.001)
        # Acceptance Scenario: Reduce from 0.001 to 0.0005 in high vol
        max_slippage = settings.RISK_SLIPPAGE_NORMAL
        if vol_status == "HIGH_VOLATILITY":
            max_slippage = settings.RISK_SLIPPAGE_HIGH_VOL
            
        # FR-003, US1: Broadcast risk parameters for Dashboard
        from src.services.telemetry_service import telemetry_service
        telemetry_service.broadcast("risk", {
            "risk_multiplier": risk_multiplier,
            "max_drawdown_pct": drawdown,
            "volatility_status": vol_status,
            "l2_entropy": l2_entropy
        })
            
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
        if inspect.isawaitable(portfolio):
            portfolio = await portfolio
        
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

    def calculate_friction(
        self,
        amount: float,
        ticker: str | float = "GENERIC",
        flat_spread: Optional[float] = None,
        fx_fee: float = 0.0,
    ) -> Dict:
        """
        T007/FR-007: Calculates friction and enforces strict micro-budget rejection.
        If trade < $5.00 and friction > 1.5%, status MUST be FRICTION_REJECT.
        """
        if isinstance(ticker, (int, float)):
            spread_pct = float(ticker) / 100.0
            commission = 0.0 if flat_spread is None else float(flat_spread)
            total_cost = (amount * spread_pct) + commission + float(fx_fee)
            friction_pct = total_cost / amount if amount > 0 else 1.0
            return {
                "total_cost": round(total_cost, 10),
                "friction_pct": friction_pct,
                "is_excessive": friction_pct > settings.MAX_FRICTION_PCT,
                "is_acceptable": friction_pct <= settings.MAX_FRICTION_PCT,
                "status": "ACCEPTED" if friction_pct <= settings.MAX_FRICTION_PCT else "FRICTION_REJECT",
                "rejection_reason": None if friction_pct <= settings.MAX_FRICTION_PCT else "Friction exceeds limit",
            }
        spread = settings.T212_FLAT_SPREAD_USD if flat_spread is None else flat_spread
        res = self.fee_analyzer.check_fees(ticker=ticker, amount_fiat=amount, flat_spread=spread)
        
        status = "ACCEPTED"
        # Decision 4 / FR-007: Micro-budget threshold check
        if amount < settings.MICRO_TRADE_THRESHOLD_USD and not res["is_acceptable"]:
            status = "FRICTION_REJECT"
            
        return {
            "status": status,
            "is_acceptable": res["is_acceptable"] if status == "ACCEPTED" else False,
            "friction_pct": res["total_friction_percent"],
            "rejection_reason": res["rejection_reason"]
        }

    def is_trade_allowed(self, amount: float, friction_pct: float) -> Dict:
        if amount < settings.MIN_TRADE_VALUE:
            return {"allowed": False, "reason": f"Trade value below minimum {settings.MIN_TRADE_VALUE:.2f}"}
        if friction_pct > settings.MAX_FRICTION_PCT:
            return {"allowed": False, "reason": f"Friction exceeds limit {settings.MAX_FRICTION_PCT:.2%}"}
        return {"allowed": True, "reason": "OK"}

    def trigger_sector_freeze(self, sector: str, rationale: str, duration_seconds: int = 3600) -> None:
        self.sector_freezes[sector] = datetime.now() + timedelta(seconds=duration_seconds)

    def is_sector_frozen(self, sector: str) -> bool:
        expires_at = self.sector_freezes.get(sector)
        if not expires_at:
            return False
        if expires_at <= datetime.now():
            self.sector_freezes.pop(sector, None)
            return False
        return True

    def validate_trade(
        self,
        ticker: str,
        total_portfolio_cash: float,
        amount_fiat: float,
        win_prob: float = settings.DEFAULT_WIN_PROBABILITY,
        win_loss_ratio: float = settings.DEFAULT_WIN_LOSS_RATIO,
        hedging_state: str = "NORMAL",
    ) -> Dict:
        """
        Performs full risk validation for a proposed trade.
        Uses Half-Kelly and enforces max configured portfolio exposure per trade.
        """
        # DEFCON 1 Veto: Reject high-volatility long trades if market risk is extreme
        if hedging_state == "DEFCON_1" and ticker not in self.inverse_etfs.values():
            return {
                "ticker": ticker,
                "is_acceptable": False,
                "rejection_reason": "DEFCON_1: Market risk extreme. Long trades suppressed."
            }

        fee_check = self.fee_analyzer.check_fees(ticker, amount_fiat)
        
        # User-defined overrides for Kelly inputs.
        kelly_fraction = self.kelly_calculator.calculate_size(win_prob, win_loss_ratio)
        
        # HALF-KELLY constraint
        half_kelly_fraction = kelly_fraction / 2.0
        
        # Max allocation cap of portfolio total value per position
        max_allowed_fiat = total_portfolio_cash * (settings.MAX_ALLOCATION_PERCENTAGE / 100.0)
        
        # Proposed value using the adjusted Kelly multiplied by the configured standard allocation or the entire portfolio (scaled). We fallback to minimum of calculated ones.
        proposed_fiat = amount_fiat * half_kelly_fraction
        # L-11: Use Decimal arithmetic and round to cents to avoid float drift in 5%-equity enforcement
        final_amount = float(
            min(
                Decimal(str(proposed_fiat)),
                Decimal(str(max_allowed_fiat))
            ).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        )
        
        # Ensure minimum friction limits are kept
        is_acceptable = fee_check["is_acceptable"] and final_amount >= settings.MIN_TRADE_VALUE
        
        return {
            "ticker": ticker,
            "is_acceptable": is_acceptable,
            "fee_status": fee_check,
            "kelly_fraction": half_kelly_fraction,
            "final_amount": final_amount if is_acceptable else 0.0,
            "rejection_reason": fee_check["rejection_reason"] if not is_acceptable else ""
        }

    def check_financial_kill_switch(
        self,
        position_current_value: float,
        position_cost_basis: float,
        max_loss_pct: float = settings.FINANCIAL_KILL_SWITCH_PCT,
    ) -> bool:
        """
        Hard financial stop-loss guard. If position loses more than maximum loss percentage (2% default).
        Returns True if Kill switch triggered (abort position).
        """
        if position_cost_basis <= 0: return False
        
        loss_pct = (position_cost_basis - position_current_value) / position_cost_basis
        if loss_pct >= max_loss_pct:
            return True
        return False

    def get_all_sector_exposures(self, portfolio: List[Dict]) -> Dict[str, float]:
        """
        Calculates the sector exposure of the active portfolio as a percentage.
        portfolio format expected: [{"ticker": str, "size": float, "sector": str}]
        """
        if not portfolio:
            return {}
            
        total_size = sum(p.get("size", 0.0) for p in portfolio)
        if total_size == 0.0:
            return {}
            
        exposures = {}
        for p in portfolio:
            sector = p.get("sector", "General")
            size = p.get("size", 0.0)
            exposures[sector] = exposures.get(sector, 0.0) + size
            
        for sector in exposures:
            exposures[sector] = exposures[sector] / total_size
            
        return exposures

risk_service = RiskService()

class PortfolioOptimizer:
    def calculate_covariance(self, returns_df):
        """
        Calculates the covariance matrix for a set of asset returns.
        """
        return returns_df.cov()

    def get_sharpe_ratio(self, returns, risk_free_rate: float = settings.PORTFOLIO_RISK_FREE_RATE):
        """
        Calculates the Sharpe Ratio.
        """
        mean_return = returns.mean()
        std_dev = returns.std()
        if std_dev == 0:
            return 0.0
        return (mean_return - risk_free_rate) / std_dev
