from typing import Dict
from src.models.persistence import PersistenceManager
from src.config import settings

class ShadowService:
    def __init__(self):
        self.persistence = PersistenceManager(settings.DB_PATH)

    async def execute_simulated_trade(self, pair_id: str, direction: str, size_a: float, size_b: float, price_a: float, price_b: float):
        """
        Records a simulated trade in the Virtual Ledger.
        """
        trade_id = self.persistence.save_trade(pair_id, direction, size_a, size_b, is_shadow=True)
        # Update entry prices in persistence (requires expanding the save_trade helper or direct SQL)
        print(f"SHADOW TRADE EXECUTED: {direction} for {pair_id} at {price_a}/{price_b}")
        return trade_id

shadow_service = ShadowService()
