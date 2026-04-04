import json
import logging
from datetime import datetime
from src.models.persistence import PersistenceManager
from src.config import settings
import quantstats as qs

logger = logging.getLogger(__name__)

class AuditService:
    def __init__(self):
        self.persistence = PersistenceManager(settings.DB_PATH)
        self.total_cycles = 0
        self.successful_cycles = 0

    def log_cycle(self, success: bool = True):
        """Tracks monitoring loop iterations."""
        self.total_cycles += 1
        if success:
            self.successful_cycles += 1

    def get_connectivity_rate(self) -> float:
        """Calculates success rate."""
        if self.total_cycles == 0:
            return 100.0
        return (self.successful_cycles / self.total_cycles) * 100.0

    def log_thought_process(self, signal_id: str, agent_state: dict):
        """
        Persists the reasoning behind a decision with SHAP/LIME-style attribution (Principle III).
        """
        signal_ctx = agent_state.get('signal_context', {})
        sector = signal_ctx.get('sector', 'Unknown')
        exposure = signal_ctx.get('sector_exposure', 0.0)
        beta = signal_ctx.get('dynamic_beta', 1.0)
        z_score = signal_ctx.get('z_score', 0.0)
        
        # Feature 009: Adversarial Fundamental Analysis
        f_verdict = agent_state.get('fundamental_verdict', {})
        f_rationale = f_verdict.get('rationale', 'No Fundamental analysis available')
        f_score = f_verdict.get('integrity_score', 50)
        
        # 1. Agent Baseline Attribution (SHAP-lite)
        b_conf = agent_state.get('bull_verdict', {}).get('confidence', 0.5)
        r_conf = 1.0 - agent_state.get('bear_verdict', {}).get('confidence', 0.5)
        f_conf = f_score / 100.0
        
        avg_base = (b_conf + r_conf + f_conf) / 3
        
        # 2. LIME-style Feature Influence (Fundamental specifics)
        # We attribute the score deviation to specific "Prosecutor" or "Defender" findings
        risks = f_verdict.get('risk_factors', [])
        strengths = f_verdict.get('strengths', [])
        
        # Weights for fundamental features (LIME approximation)
        feature_importance = {
            "prosecutor_risks": -len(risks) * 0.25,
            "defender_strengths": len(strengths) * 0.30,
            "sector_contagion": -0.1 if exposure > 0.05 else 0.0
        }

        shap = {
            "bull_contribution": round(b_conf - avg_base, 3),
            "bear_contribution": round(r_conf - avg_base, 3),
            "fundamental_contribution": round(f_conf - avg_base, 3),
            "feature_influence": feature_importance,
            "sector_impact": exposure,
            "dynamic_beta": beta
        }

        self.persistence.log_thought(
            signal_id=signal_id,
            bull=agent_state.get('bull_verdict', {}).get('argument', 'N/A'),
            bear=agent_state.get('bear_verdict', {}).get('argument', 'N/A'),
            news=f_rationale,
            verdict=f"[{sector} Exp: {exposure:.1%}] [Beta: {beta:.2f}] [Score: {f_score}] " + agent_state.get('final_verdict', ''),
            shap=shap,
            fundamental_impact=round(f_conf - 0.5, 3),
            sec_ref=risks[0] if risks else (strengths[0] if strengths else "N/A")
        )
        logger.info(f"AUDIT: Adversarial thought Journal persisted for signal {signal_id} (Score: {f_score})")

    def generate_daily_report(self):
        """
        Generates QuantStats HTML report and includes sector analysis.
        """
        from src.services.shadow_service import shadow_service
        from src.services.risk_service import risk_service

        # 1. Fetch current sector exposures
        portfolio = shadow_service.get_active_portfolio_with_sectors()
        exposures = risk_service.get_all_sector_exposures(portfolio)

        print("AUDIT: Generating daily report with sector analysis...")
        if exposures:
            print(f"AUDIT: Sector Concentration: {json.dumps(exposures)}")

        # Mocking QuantStats report generation
        # In production, we'd query historical returns from trade_records
        # qs.reports.html(returns_series, output="reports/tearsheet.html")
        print("AUDIT: QuantStats tearsheet created (mocked).")

audit_service = AuditService()

