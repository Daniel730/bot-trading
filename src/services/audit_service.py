import json
import logging
from datetime import datetime
from src.services.persistence_service import persistence_service, DecisionType
from src.config import settings
import uuid

logger = logging.getLogger(__name__)

class AuditService:
    def __init__(self):
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

    async def log_thought_process(self, signal_id: str, agent_state: dict):
        """
        Persists the reasoning behind a decision with SHAP/LIME-style attribution.
        Uses the new PostgreSQL AgentReasoning model.
        """
        signal_ctx = agent_state.get('signal_context', {})
        ticker_a = signal_ctx.get('ticker_a', 'N/A')
        ticker_b = signal_ctx.get('ticker_b', 'N/A')
        pair_name = f"{ticker_a}_{ticker_b}"
        
        exposure = signal_ctx.get('sector_exposure', 0.0)
        beta = signal_ctx.get('dynamic_beta', 1.0)
        
        f_verdict = agent_state.get('fundamental_verdict', {})
        f_score = f_verdict.get('integrity_score', 50)
        
        b_conf = agent_state.get('bull_verdict', {}).get('confidence', 0.5)
        r_conf = 1.0 - agent_state.get('bear_verdict', {}).get('confidence', 0.5)
        f_conf = f_score / 100.0
        
        avg_base = (b_conf + r_conf + f_conf) / 3
        
        shap = {
            "bull_contribution": round(b_conf - avg_base, 3),
            "bear_contribution": round(r_conf - avg_base, 3),
            "fundamental_contribution": round(f_conf - avg_base, 3),
            "sector_impact": exposure,
            "dynamic_beta": beta
        }

        # Map decision to Enum
        final_verdict_str = agent_state.get('final_verdict', '').upper()
        decision = DecisionType.HOLD
        if "BUY" in final_verdict_str: decision = DecisionType.BUY
        elif "SELL" in final_verdict_str: decision = DecisionType.SELL
        elif "VETO" in final_verdict_str: decision = DecisionType.VETO

        reasoning_data = {
            "trace_id": uuid.UUID(signal_id) if isinstance(signal_id, str) and len(signal_id) == 36 else uuid.uuid4(),
            "agent_name": "Orchestrator",
            "ticker_pair": pair_name,
            "thought_journal": agent_state.get('final_verdict', 'No journal provided'),
            "risk_metrics": shap,
            "decision": decision
        }

        await persistence_service.log_reasoning(reasoning_data)
        logger.info(f"AUDIT: Agent reasoning persisted for {pair_name} (Decision: {decision.name})")

audit_service = AuditService()
