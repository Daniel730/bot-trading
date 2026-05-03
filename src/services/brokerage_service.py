import asyncio
import logging
from typing import List, Dict, Any, Optional
from src.config import settings
from src.services.budget_service import budget_service
from src.services.brokerage.alpaca import AlpacaProvider

logger = logging.getLogger(__name__)

class AwaitableList(list):
    def __await__(self):
        async def _coro():
            return self
        return _coro().__await__()

class AwaitableFloat(float):
    def __await__(self):
        async def _coro():
            return float(self)
        return _coro().__await__()

class BrokerageService:
    """
    BrokerageService facade, now simplified to focus on Alpaca as the primary provider.
    Legacy providers (T212, Web3) have been moved to legacy/.
    """
    def __init__(self, provider_name: str = None):
        self.configure_provider(provider_name)

    def configure_provider(self, provider_name: str = None):
        """
        Always initializes with AlpacaProvider as requested by the user.
        """
        if provider_name and provider_name.strip().upper() != "ALPACA":
            logger.warning("BrokerageService: %s is legacy-only; using ALPACA.", provider_name)
        self.provider_name = "ALPACA"
        self.provider = AlpacaProvider()
        logger.info("BrokerageService: Initialized with ALPACA provider (Legacy providers moved to legacy/).")

    def test_connection(self) -> bool:
        return self.provider.test_connection()

    def get_venue(self, ticker: str) -> str:
        return self.provider_name

    async def place_market_order(self, ticker: str, quantity: float, side: str, limit_price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        result = await self.provider.place_market_order(ticker, quantity, side, limit_price, client_order_id)
        result["venue"] = self.provider_name
        return result

    async def place_value_order(self, ticker: str, amount: float, side: str, price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        result = await self.provider.place_value_order(ticker, amount, side, price, client_order_id)
        result["venue"] = self.provider_name
        if result.get("status") != "error" and not settings.PAPER_TRADING:
            budget_service.update_used_budget(self.provider_name, amount)
        return result

    def get_symbol_metadata(self, ticker: str) -> Dict[str, Any]:
        return self.provider.get_symbol_metadata(ticker)

    async def is_asset_active(self, ticker: str) -> bool:
        return await self.provider.is_asset_active(ticker)

    async def get_portfolio(self) -> List[Dict[str, Any]]:
        data = await asyncio.to_thread(self.provider.get_portfolio)
        return AwaitableList(data)

    async def get_positions(self, ticker: str = None) -> List[Dict[str, Any]]:
        data = await asyncio.to_thread(self.provider.get_positions, ticker)
        return AwaitableList(data)

    async def get_available_quantity(self, ticker: str) -> float:
        positions = await self.get_positions(ticker)
        for pos in positions:
            pos_ticker = pos.get("ticker", "")
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
        val = await asyncio.to_thread(self.provider.get_account_cash)
        return AwaitableFloat(val)

    async def get_account_equity(self) -> float:
        val = await asyncio.to_thread(self.provider.get_account_equity)
        return AwaitableFloat(val)

    async def get_account_buying_power(self) -> float:
        val = await asyncio.to_thread(self.provider.get_account_buying_power)
        return AwaitableFloat(val)

    async def get_pending_orders_value(self) -> float:
        orders = await self.get_pending_orders()
        total_value = 0.0
        for order in orders:
            try:
                qty = float(order.get('quantity', 0.0) or 0.0)
            except (TypeError, ValueError):
                qty = 0.0
            if qty > 0:
                try:
                    price = float(order.get('limitPrice') or order.get('price') or 0.0)
                except (TypeError, ValueError):
                    price = 0.0
                if price <= 0.0:
                    from src.services.data_service import data_service
                    ticker = order.get('ticker')
                    prices = await data_service.get_latest_price_async([ticker])
                    try:
                        price = float(prices.get(ticker, 0.0) or 0.0)
                    except (TypeError, ValueError):
                        price = 0.0
                total_value += (qty * price)
        return AwaitableFloat(total_value)

brokerage_service = BrokerageService()
