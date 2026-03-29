import json
from datetime import datetime
from src.models.persistence import PersistenceManager
from src.config import settings
import quantstats as qs

class AuditService:
    def __init__(self):
        self.persistence = PersistenceManager(settings.DB_PATH)

    def log_thought_process(self, signal_id: str, agent_state: dict):
        """
        Persists the reasoning behind a decision.
        """
        self.persistence.log_thought(
            signal_id=signal_id,
            bull=agent_state['bull_verdict']['argument'],
            bear=agent_state['bear_verdict']['argument'],
            news=agent_state['news_verdict']['reasoning'],
            verdict=agent_state['reasoning'],
            shap={"baseline_impact": 0.45, "news_impact": 0.55} # Mock SHAP
        )
        print(f"AUDIT: Thought Journal persisted for signal {signal_id}")

    def generate_daily_report(self):
        """
        Generates QuantStats HTML report.
        """
        # In a real scenario, this would query trade_records for returns
        # Mocking a report generation
        print("AUDIT: Generating daily QuantStats report...")
        # qs.reports.html(returns_series, output="reports/tearsheet.html")

audit_service = AuditService()
