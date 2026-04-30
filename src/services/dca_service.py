import asyncio
import inspect
from datetime import datetime, timedelta
from typing import Dict
from src.services.persistence_service import persistence_service, FrequencyType
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
    def __init__(self, db=None):
        self._running = False
        self.drip_manager = DRIPManager()
        self.db = db

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
                    new_next_run = self.calculate_next_run(schedule.frequency, schedule.next_run)
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

    async def execute_dca(self, allocation: dict):
        from src.agents.portfolio_manager_agent import portfolio_manager
        return await portfolio_manager.allocate_funds(
            allocation["strategy_id"],
            float(allocation["amount"]),
        )

    async def process_pending_dca(self) -> int:
        if self.db is None:
            return 0

        now = datetime.now()
        executed_count = 0
        for schedule in self.db.get_active_dca_schedules():
            next_run = datetime.fromisoformat(schedule["next_run"])
            if next_run > now:
                continue
            await self.execute_dca(schedule)
            frequency = str(schedule["frequency"]).lower()
            self.db.update_dca_next_run(
                schedule["id"],
                self.calculate_next_run(frequency, next_run),
            )
            executed_count += 1
        return executed_count

    async def sweep_dividends(self):
        from src.models.persistence import PersistenceManager
        from src.services.brokerage_service import BrokerageService

        db = self.db or PersistenceManager(settings.DB_PATH)
        if db.get_fee_config("drip_enabled", 0.0) != 1.0:
            return {"status": "disabled"}

        cash = await BrokerageService().get_account_cash()
        min_trade_value = db.get_fee_config("min_trade_value", settings.MIN_TRADE_VALUE)
        if cash < min_trade_value:
            return {"status": "skipped", "reason": "below_min_trade_value"}

        allocation = {"strategy_id": "safe", "amount": float(cash)}
        result = self.execute_dca(allocation)
        if inspect.isawaitable(result):
            await result
        return {"status": "success", **allocation}

    def calculate_next_run(self, frequency: FrequencyType | str, last_run: datetime) -> datetime:
        frequency_value = frequency.value if hasattr(frequency, "value") else str(frequency).lower()
        if frequency_value == "daily":
            return last_run + timedelta(days=1)
        elif frequency_value == "weekly":
            return last_run + timedelta(weeks=1)
        elif frequency_value == "monthly":
            return last_run + timedelta(days=30)
        return last_run + timedelta(days=1)

    def _calculate_next_run(self, frequency: FrequencyType, last_run: datetime) -> datetime:
        return self.calculate_next_run(frequency, last_run)

    def is_market_open(self) -> bool:
        if settings.DEV_MODE:
            return True
        now = datetime.now()
        if now.weekday() >= 5:
            return False

        def int_setting(name: str, default: int) -> int:
            value = getattr(settings, name, default)
            return value if isinstance(value, int) and not isinstance(value, bool) else default

        start = now.replace(
            hour=int_setting("START_HOUR", 9),
            minute=int_setting("START_MINUTE", 30),
            second=0,
            microsecond=0,
        )
        end = now.replace(
            hour=int_setting("END_HOUR", 16),
            minute=int_setting("END_MINUTE", 0),
            second=0,
            microsecond=0,
        )
        return start <= now <= end

    def stop(self):
        self._running = False

dca_service = DCAService()
