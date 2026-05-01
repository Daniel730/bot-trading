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
        """
        Initialize the BrokerageService with a selected brokerage provider and the web3 service.
        
        Parameters:
            provider_name (str, optional): The brokerage provider identifier to use. If omitted, the provider is taken from settings.BROKERAGE_PROVIDER. The selected provider is instantiated and assigned to `self.provider`; `self.provider_name` and `self.web3` are also set.
        """
        self.web3 = web3_service
        self.configure_provider(provider_name)

    def configure_provider(self, provider_name: str = None):
        """
        Recreate the active equity brokerage provider from runtime settings.

        Parameters:
            provider_name (str, optional): Explicit provider override. When omitted,
            uses settings.BROKERAGE_PROVIDER so dashboard config changes can be
            applied without restarting the process.
        """
        selected_provider = (provider_name or settings.BROKERAGE_PROVIDER or "T212").strip().upper()
        self.provider_name = selected_provider

        if selected_provider == "ALPACA":
            self.provider = AlpacaProvider()
            logger.info("BrokerageService: Initialized with ALPACA provider.")
        else:
            self.provider_name = "T212"
            self.provider = T212Provider()
            logger.info("BrokerageService: Initialized with T212 provider.")

    def test_connection(self) -> bool:
        """
        Checks connectivity to the active brokerage provider.
        
        Returns:
            true if the provider is reachable and credentials are valid, false otherwise.
        """
        return self.provider.test_connection()

    def get_venue(self, ticker: str) -> str:
        """
        Determines whether a ticker should be routed to the WEB3 venue or the active brokerage.
        
        Parameters:
            ticker (str): The instrument symbol; matching is case-insensitive and based on the presence of the substring "-USD".
        
        Returns:
            str: `"WEB3"` if `"-USD"` appears in `ticker` (case-insensitive), otherwise the active provider name.
        """
        return "WEB3" if "-USD" in ticker.upper() else self.provider_name

    async def place_market_order(self, ticker: str, quantity: float, side: str, limit_price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        """
        Places a market order using the active brokerage provider or the WEB3 service when applicable.
        
        Parameters:
            ticker (str): Instrument symbol to trade.
            quantity (float): Quantity to buy or sell.
            side (str): Order side, e.g., "buy" or "sell".
            limit_price (float, optional): Optional execution cap price if supported by the provider.
            client_order_id (str, optional): Optional client-specified identifier for the order.
        
        Returns:
            dict: Response from the provider or WEB3 service containing order details or an error description.
        """
        venue = self.get_venue(ticker)
        if venue == "WEB3" and not settings.PAPER_TRADING:
             return await self.web3.place_market_order(ticker, quantity, side)
        
        return await self.provider.place_market_order(ticker, quantity, side, limit_price, client_order_id)

    async def place_value_order(self, ticker: str, amount: float, side: str, price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        """
        Place a fiat-value order for a ticker through the appropriate venue.
        
        Routes the request to the WEB3 service when the ticker denotes a WEB3 asset and paper trading is disabled; otherwise routes to the configured brokerage provider. On successful execution (result["status"] != "error") and when not in paper trading mode, updates the used budget for the chosen venue.
        
        Parameters:
            ticker (str): Asset identifier to buy or sell.
            amount (float): Fiat amount to spend for a `buy` or to receive for a `sell`.
            side (str): Order side, e.g., "buy" or "sell".
            price (float, optional): Optional price to include for provider-side value orders when supported.
            client_order_id (str, optional): Optional client-supplied identifier forwarded to the provider.
        
        Returns:
            Dict[str, Any]: The provider or web3 response dictionary augmented with a "venue" key indicating where the order was placed. On failure `result["status"]` is expected to be `"error"`.
        """
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
        """
        Retrieve metadata for a trading symbol.
        
        Parameters:
            ticker (str): The ticker symbol to look up.
        
        Returns:
            Dict[str, Any]: A dictionary containing metadata for the symbol (for example: name, exchange, trading increments, and other provider-specific fields).
        """
        return self.provider.get_symbol_metadata(ticker)

    async def get_portfolio(self) -> List[Dict[str, Any]]:
        # Maintaining AwaitableList behavior for backward compatibility
        """
        Return the account portfolio from the active provider as an awaitable list for backward compatibility.
        
        Each item in the returned list is a provider-specific position dictionary.
        
        Returns:
            AwaitableList: A list-like wrapper around portfolio position dictionaries for asynchronous consumption.
        """
        data = await asyncio.to_thread(self.provider.get_portfolio)
        return AwaitableList(data)

    async def get_positions(self, ticker: str = None) -> List[Dict[str, Any]]:
        """
        Retrieve current positions, optionally filtered by a ticker symbol.
        
        Parameters:
            ticker (str, optional): Ticker symbol to filter returned positions. If omitted, returns all positions.
        
        Returns:
            List[Dict[str, Any]]: A list-like container of position dictionaries, each representing a current holding. Fields are provider-specific.
        """
        data = await asyncio.to_thread(self.provider.get_positions, ticker)
        return AwaitableList(data)

    async def get_available_quantity(self, ticker: str) -> float:
        """
        Retrieve the available tradable quantity for a given ticker from the account's positions.
        
        Matches a position whose `ticker` equals the provided `ticker` or starts with it. Uses the position's `quantityAvailableForTrading` when present, otherwise falls back to `quantity`. Returns 0.0 if no matching position is found.
        
        Parameters:
            ticker (str): The normalized ticker to look up; providers are expected to return normalized `ticker` values.
        
        Returns:
            float: Available quantity for trading for the matched ticker, or 0.0 if none.
        """
        positions = await self.get_positions(ticker)
        for pos in positions:
            pos_ticker = pos.get("ticker", "")
            # Match on the canonical ticker; providers are responsible for
            # returning the normalised (non-broker-formatted) ticker key.
            if pos_ticker == ticker or pos_ticker.startswith(ticker):
                return float(pos.get("quantityAvailableForTrading", pos.get("quantity", 0.0)) or 0.0)
        return 0.0

    async def get_pending_orders(self) -> List[Dict[str, Any]]:
        """
        Get pending orders from the active brokerage provider.
        
        Wraps the provider's pending orders list in an AwaitableList for use in async contexts.
        
        Returns:
            AwaitableList: A list-like AwaitableList containing pending order dictionaries as returned by the provider.
        """
        data = await asyncio.to_thread(self.provider.get_pending_orders)
        return AwaitableList(data)

    async def has_pending_order(self, ticker: str) -> bool:
        """
        Check whether there is a pending order for the given ticker.
        
        Returns:
            `true` if a pending order exists for `ticker`, `false` otherwise.
        """
        orders = await self.get_pending_orders()
        return any(o.get('ticker') == ticker for o in orders)

    async def is_ticker_owned(self, ticker: str) -> bool:
        """
        Return whether the account holds a position for the given ticker.
        
        Returns:
            `true` if a position with `ticker` exists in the portfolio, `false` otherwise.
        """
        portfolio = await self.get_portfolio()
        return any(pos.get('ticker') == ticker for pos in portfolio)

    async def get_account_cash(self) -> float:
        # Maintaining AwaitableFloat behavior for backward compatibility
        """
        Get the account cash balance.
        
        Returns:
            AwaitableFloat: The account cash balance as a float wrapped in an AwaitableFloat for backward compatibility.
        """
        val = await asyncio.to_thread(self.provider.get_account_cash)
        return AwaitableFloat(val)

    async def get_pending_orders_value(self) -> float:
        """
        Compute the total fiat value of pending orders.
        
        Each pending order contributes quantity * price. When the broker reports
        a zero/missing order price, fall back to the latest market price for the
        order ticker so budget checks do not undercount pending commitments.
        
        Returns:
            total_value (float): Sum of quantity * (limitPrice or price) for all pending orders with quantity > 0.
        """
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
