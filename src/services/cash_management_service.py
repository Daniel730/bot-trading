from src.models.persistence import PersistenceManager
from src.services.brokerage_service import brokerage_service
from src.services.agent_log_service import agent_trace
from src.config import settings
import logging

logger = logging.getLogger(__name__)

class CashManagementService:
    def __init__(self, db_path: str = "trading_bot.db"):
        self.persistence = PersistenceManager(db_path)
        self.sweep_ticker = getattr(settings, "SGOV_SWEEP_TICKER", "SGOV")
        self.min_threshold = getattr(settings, "MIN_SWEEP_THRESHOLD", 10.0)

    @agent_trace("CashManagementService.sweep_idle_cash")
    async def sweep_idle_cash(self):
        """
        Checks uninvested balance and buys SGOV if above threshold.
        """
        cash = await brokerage_service.get_account_cash()
        if cash > self.min_threshold:
            logger.info(f"CashManagement: Sweeping ${cash:.2f} into {self.sweep_ticker}")
            result = await brokerage_service.execute_order(self.sweep_ticker, cash, side="buy")
            if result.get("status") != "error":
                self.persistence.save_cash_sweep("SWEEP_IN", cash, self.sweep_ticker, 0.0)
                return cash
        return 0.0

    @agent_trace("CashManagementService.liquidate_for_trade")
    async def liquidate_for_trade(self, target_amount: float) -> float:
        """
        Sells fractional amount of sweep vehicle to fund a trade.
        """
        portfolio = await brokerage_service.get_portfolio()
        sweep_pos = next((p for p in portfolio if p['ticker'] == brokerage_service._format_ticker(self.sweep_ticker)), None)
        
        if not sweep_pos:
            logger.warning(f"CashManagement: No {self.sweep_ticker} position found to liquidate.")
            return 0.0
        
        # In v0, portfolio item usually has 'ppl' (profit/loss) and 'averagePrice', 'quantity'
        # We need the current value.
        current_price = sweep_pos.get('averagePrice', 0.0) # Simplified fallback
        # Ideally we'd get the latest price from DataService
        from src.services.data_service import data_service
        prices = await data_service.get_latest_price([self.sweep_ticker])
        if self.sweep_ticker in prices:
            current_price = prices[self.sweep_ticker]
            
        pos_value = sweep_pos.get('quantity', 0.0) * current_price
        
        liquidate_amount = min(target_amount, pos_value)
        if liquidate_amount > 0:
            logger.info(f"CashManagement: Liquidating ${liquidate_amount:.2f} of {self.sweep_ticker}")
            result = await brokerage_service.execute_order(self.sweep_ticker, liquidate_amount, side="sell")
            if result.get("status") != "error":
                self.persistence.save_cash_sweep("SWEEP_OUT", liquidate_amount, self.sweep_ticker, pos_value - liquidate_amount)
                return liquidate_amount
        
        return 0.0

cash_management_service = CashManagementService()
