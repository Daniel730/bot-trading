import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from src.models.persistence import PersistenceManager
from src.services.brokerage_service import brokerage_service
from src.services.agent_log_service import agent_trace

from src.config import settings

class DRIPManager:
    """Manages micro-dividend accumulation and sweep logic."""
    def __init__(self, min_sweep_threshold: float = 1.0):
        self.min_sweep_threshold = min_sweep_threshold
        self.balances: Dict[str, float] = {}

    def add_dividend(self, ticker: str, amount: float):
        self.balances[ticker] = self.balances.get(ticker, 0.0) + amount

    def get_balance(self, ticker: str) -> float:
        return self.balances.get(ticker, 0.0)

    def should_sweep(self, ticker: str) -> bool:
        return self.get_balance(ticker) >= self.min_sweep_threshold

    def sweep(self, ticker: str) -> float:
        amount = self.get_balance(ticker)
        self.balances[ticker] = 0.0
        return amount

class DCAService:
    def __init__(self, db: Optional[PersistenceManager] = None):
        self.persistence = db if db else PersistenceManager(settings.DB_PATH)
        self._running = False
        self.drip_manager = DRIPManager()

    async def process_pending_dca(self) -> int:
        """Processes all active DCA schedules that are due (T013)."""
        schedules = self.persistence.get_active_dca_schedules()
        executed_count = 0
        now = datetime.now()

        for schedule in schedules:
            next_run = datetime.fromisoformat(schedule["next_run"])
            if now >= next_run:
                await self._execute_dca(schedule)
                # Update next run logic...
                executed_count += 1
        return executed_count

    def handle_dividend(self, ticker: str, amount: float):
        """Processes an incoming dividend (T015)."""
        self.drip_manager.add_dividend(ticker, amount)
        if self.drip_manager.should_sweep(ticker):
            sweep_amount = self.drip_manager.sweep(ticker)
            # await self._execute_reinvestment(ticker, sweep_amount)
            print(f"DRIP Sweep: Reinvesting ${sweep_amount} into {ticker}")

    @agent_trace("DCAService.process_schedules")
    async def process_schedules(self):
        """
        Periodically checks for active DCA schedules and executes them.
        """
        self._running = True
        while self._running:
            now = datetime.now()
            schedules = self.persistence.get_active_dca_schedules()
            
            for schedule in schedules:
                next_run = datetime.fromisoformat(schedule['next_run'])
                if now >= next_run:
                    await self._execute_dca(schedule)
                    
                    # Calculate next run based on frequency
                    new_next_run = self._calculate_next_run(schedule['frequency'], next_run)
                    self.persistence.update_dca_next_run(schedule['id'], new_next_run)
            
            await asyncio.sleep(60) # Check every minute

    async def _execute_dca(self, schedule: Dict):
        """
        Executes a single DCA investment based on the strategy.
        """
        strategy_id = schedule['strategy_id']
        amount = schedule['amount']
        
        assets = self.persistence.get_portfolio_strategy(strategy_id)
        if not assets:
            self.persistence.log_event("ERROR", "DCAService", f"No assets found for strategy {strategy_id}")
            return

        self.persistence.log_event("INFO", "DCAService", f"Executing DCA for schedule {schedule['id']} - Total: ${amount}")
        
        for asset in assets:
            ticker = asset['ticker']
            weight = asset['target_weight']
            asset_amount = amount * weight
            
            if asset_amount > 0:
                # Execute value-based fractional order
                try:
                    # BrokerageService handles the fractional logic
                    await brokerage_service.execute_order(ticker, asset_amount, side="buy")
                    self.persistence.log_event("INFO", "DCAService", f"Invested ${asset_amount:.2f} in {ticker}")
                except Exception as e:
                    self.persistence.log_event("ERROR", "DCAService", f"Failed to invest in {ticker}: {e}")

    def _calculate_next_run(self, frequency: str, last_run: datetime) -> datetime:
        if frequency == "daily":
            return last_run + timedelta(days=1)
        elif frequency == "weekly":
            return last_run + timedelta(weeks=1)
        elif frequency == "monthly":
            # Simplified monthly
            return last_run + timedelta(days=30)
        return last_run + timedelta(days=1)

    def stop(self):
        self._running = False

dca_service = DCAService()
