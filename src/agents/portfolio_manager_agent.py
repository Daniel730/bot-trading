import logging
from datetime import datetime
from typing import Dict, List, Optional
from src.models.persistence import PersistenceManager

class PortfolioManagerAgent:
    def __init__(self, db: PersistenceManager):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def get_current_horizon(self, user_id: str) -> str:
        """
        Calculates the investment horizon based on closest goal or life event.
        """
        goals = self.db.get_investment_goals()
        life_events = self._get_user_life_events(user_id)
        
        # Determine closest deadline
        deadlines = []
        for g in goals:
            deadlines.append(datetime.fromisoformat(g["deadline"]))
        for e in life_events:
            deadlines.append(datetime.fromisoformat(e["event_date"]))
            
        if not deadlines:
            return "Long-Term"
            
        closest = min(deadlines)
        days_remaining = (closest - datetime.now()).days
        
        if days_remaining < 90:
            return "Short-Term"
        elif days_remaining < 365:
            return "Mid-Term"
        else:
            return "Long-Term"

    def _get_user_life_events(self, user_id: str) -> List[Dict]:
        """Fetches reported life events from DB."""
        with self.db._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM user_life_events WHERE user_id = ? ORDER BY event_date ASC",
                (user_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    async def orchestrate_trade(self, user_id: str, ticker: str, base_signals: List[Dict]):
        """
        High-level decision logic combining horizon, macro state, and agent signals.
        """
        horizon = self.get_current_horizon(user_id)
        # Further implementation would integrate MacroEconomicAgent and RiskService
        self.logger.info(f"Orchestrating trade for {ticker} (Horizon: {horizon})")
