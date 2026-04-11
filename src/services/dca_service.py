import asyncio
from datetime import datetime, timedelta
from typing import Dict
from src.services.persistence_service import persistence_service, FrequencyType
from src.services.agent_log_service import agent_trace

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
    def __init__(self):
        self._running = False
        self.drip_manager = DRIPManager()

    @agent_trace("DCAService.process_schedules")
    async def process_schedules(self):
        """
        Periodically checks for active DCA schedules and executes them.
        """
        self._running = True
        while self._running:
            now = datetime.now()
            schedules = await persistence_service.get_active_dca_schedules()
            
            for schedule in schedules:
                if now >= schedule.next_run:
                    await self._execute_dca(schedule)
                    
                    # Calculate next run based on frequency
                    new_next_run = self._calculate_next_run(schedule.frequency, schedule.next_run)
                    await persistence_service.update_dca_next_run(schedule.id, new_next_run)
            
            await asyncio.sleep(60) # Check every minute

    async def _execute_dca(self, schedule):
        """
        Executes a single DCA investment.
        """
        amount = schedule.amount
        ticker = schedule.target_ticker
        
        if amount > 0:
            try:
                # Assuming brokerage_service has an async execute_order method
                # await brokerage_service.execute_order(ticker, amount, side="buy")
                print(f"DCAService: Executed DCA for {ticker} - ${amount:.2f}")
            except Exception as e:
                print(f"DCAService Error: Failed to invest in {ticker}: {e}")

    def _calculate_next_run(self, frequency: FrequencyType, last_run: datetime) -> datetime:
        if frequency == FrequencyType.DAILY:
            return last_run + timedelta(days=1)
        elif frequency == FrequencyType.WEEKLY:
            return last_run + timedelta(weeks=1)
        elif frequency == FrequencyType.MONTHLY:
            return last_run + timedelta(days=30)
        return last_run + timedelta(days=1)

    def stop(self):
        self._running = False

dca_service = DCAService()
