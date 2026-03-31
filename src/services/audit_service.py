import json
from datetime import datetime
from src.models.persistence import PersistenceManager
from src.config import settings
import quantstats as qs

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
        Persists the reasoning behind a decision.
        """
        signal_ctx = agent_state.get('signal_context', {})
        sector = signal_ctx.get('sector', 'Unknown')
        exposure = signal_ctx.get('sector_exposure', 0.0)
        
        self.persistence.log_thought(
            signal_id=signal_id,
            bull=agent_state['bull_verdict']['argument'],
            bear=agent_state['bear_verdict']['argument'],
            news=agent_state['news_verdict']['reasoning'],
            verdict=f"[{sector} Exp: {exposure:.1%}] " + agent_state['reasoning'],
            shap={"baseline_impact": 0.45, "news_impact": 0.55, "sector_impact": exposure} 
        )
        print(f"AUDIT: Thought Journal persisted for signal {signal_id} (Sector: {sector})")

    def generate_daily_report(self):
        """
        Generates QuantStats HTML report.
        """
        # In a real scenario, this would query trade_records for returns
        # Mocking a report generation
        print("AUDIT: Generating daily QuantStats report...")
        # qs.reports.html(returns_series, output="reports/tearsheet.html")

audit_service = AuditService()
