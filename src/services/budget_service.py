import logging
from typing import Dict, Optional
from src.models.persistence import PersistenceManager
from src.config import settings

logger = logging.getLogger(__name__)

class BudgetService:
    def __init__(self, db_path: Optional[str] = None):
        self.persistence = PersistenceManager(db_path)
        self._init_budgets()

    def _init_budgets(self):
        """Initializes budget tracking in system_state if not present."""
        # We don't overwrite existing used budgets on restart
        if self.persistence.get_system_state("budget_used_T212") is None:
            self.persistence.set_system_state("budget_used_T212", 0.0)
        if self.persistence.get_system_state("budget_used_WEB3") is None:
            self.persistence.set_system_state("budget_used_WEB3", 0.0)

    def get_venue_budget_info(self, venue: str) -> Dict[str, float]:
        """
        Returns a dict with total_budget, used_budget, and remaining_budget for a venue.
        """
        total = getattr(settings, f"{venue}_BUDGET_USD", 0.0)
        used = float(self.persistence.get_system_state(f"budget_used_{venue}", 0.0))
        
        # If total is 0, it means no cap is set, but we might still track usage
        remaining = max(0.0, total - used) if total > 0 else 999999.0 # Effectively unlimited if cap is 0
        
        return {
            "total": total,
            "used": used,
            "remaining": remaining
        }

    def update_used_budget(self, venue: str, amount: float):
        """Increments the used budget for a venue."""
        current_used = float(self.persistence.get_system_state(f"budget_used_{venue}", 0.0))
        new_used = current_used + amount
        self.persistence.set_system_state(f"budget_used_{venue}", new_used)
        logger.info(f"BudgetService: Venue {venue} used budget updated to ${new_used:.2f} (+${amount:.2f})")

    def reset_budget(self, venue: str):
        """Resets the used budget for a venue to 0."""
        self.persistence.set_system_state(f"budget_used_{venue}", 0.0)
        logger.info(f"BudgetService: Venue {venue} used budget reset to 0.")

    def get_effective_cash(self, venue: str, actual_cash: float) -> float:
        """
        Returns the minimum of actual brokerage cash and remaining allocated budget.
        """
        info = self.get_venue_budget_info(venue)
        if info["total"] <= 0:
            return actual_cash
            
        return min(actual_cash, info["remaining"])

budget_service = BudgetService()
