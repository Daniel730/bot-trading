import asyncio
import logging
import inspect
from typing import List, Dict, Any, Optional
from src.config import settings
from src.services.web3_service import web3_service
from src.services.budget_service import budget_service
from src.services.brokerage.t212 import T212Provider, AwaitableList, AwaitableFloat
from src.services.brokerage.alpaca import AlpacaProvider

logger = logging.getLogger(__name__)

class BrokerageService:
    def __init__(self, provider_name: str = None):
        self.provider_name = provider_name or settings.BROKERAGE_PROVIDER
        self.web3 = web3_service
        
        if self.provider_name == "ALPACA":
            self.provider = AlpacaProvider()
            logger.info("BrokerageService: Initialized with ALPACA provider.")
        else:
            self.provider = T212Provider()
            logger.info("BrokerageService: Initialized with T212 provider.")

    def test_connection(self) -> bool:
        return self.provider.test_connection()

    def get_venue(self, ticker: str) -> str:
        """Determines the venue (WEB3 or Active Broker) for a given ticker."""
        return "WEB3" if "-USD" in ticker.upper() else self.provider_name

    async def place_market_order(self, ticker: str, quantity: float, side: str, limit_price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        venue = self.get_venue(ticker)
        if venue == "WEB3" and not settings.PAPER_TRADING:
             return await self.web3.place_market_order(ticker, quantity, side)
        
        return await self.provider.place_market_order(ticker, quantity, side, limit_price, client_order_id)

    async def place_value_order(self, ticker: str, amount: float, side: str, price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        venue = self.get_venue(ticker)
        from src.services.agent_log_service import agent_logger
        
        if venue == "WEB3" and not settings.PAPER_TRADING:
            result = await self.web3.place_value_order(ticker=ticker, amount_fiat=amount, side=side)
        else:
            result = await self.provider.place_value_order(ticker, amount, side, price, client_order_id)

        if result.get("status") != "error" and not settings.PAPER_TRADING:
            budget_service.update_used_budget(venue, amount)
            # Log fractional trade for the active broker path
            if venue != "WEB3":
                # We need quantity and price for logging if not provided in result
                # This is simplified; ideally providers return these.
                pass 

        result["venue"] = venue
        return result

    def get_symbol_metadata(self, ticker: str) -> Dict[str, Any]:
        return self.provider.get_symbol_metadata(ticker)

    async def get_portfolio(self) -> List[Dict[str, Any]]:
        # Maintaining AwaitableList behavior for backward compatibility
        data = await asyncio.to_thread(self.provider.get_portfolio)
        return AwaitableList(data)

    async def get_positions(self, ticker: str = None) -> List[Dict[str, Any]]:
        data = await asyncio.to_thread(self.provider.get_positions, ticker)
        return AwaitableList(data)

    async def get_available_quantity(self, ticker: str) -> float:
        positions = await self.get_positions(ticker)
        for pos in positions:
            pos_ticker = pos.get("ticker", "")
            # Match on the canonical ticker; providers are responsible for
            # returning the normalised (non-broker-formatted) ticker key.
            if pos_ticker == ticker or pos_ticker.startswith(ticker):
                return float(pos.get("quantityAvailableForTrading", pos.get("quantity", 0.0)) or 0.0)
        return 0.0

    async def get_pending_orders(self) -> List[Dict[str, Any]]:
        data = await asyncio.to_thread(self.provider.get_pending_orders)
        return AwaitableList(data)

    async def has_pending_order(self, ticker: str) -> bool:
        orders = await self.get_pending_orders()
        return any(o.get('ticker') == ticker for o in orders)

    async def is_ticker_owned(self, ticker: str) -> bool:
        portfolio = await self.get_portfolio()
        return any(pos.get('ticker') == ticker for pos in portfolio)

    async def get_account_cash(self) -> float:
        # Maintaining AwaitableFloat behavior for backward compatibility
        val = await asyncio.to_thread(self.provider.get_account_cash)
        return AwaitableFloat(val)

    async def get_pending_orders_value(self) -> float:
        orders = await self.get_pending_orders()
        total_value = 0.0
        for order in orders:
            qty = order.get('quantity', 0.0)
            if qty > 0:
                price = order.get('limitPrice') or order.get('price', 0.0)
                total_value += (qty * price)
        return AwaitableFloat(total_value)

brokerage_service = BrokerageService()
