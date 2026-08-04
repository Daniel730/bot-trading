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
    Legacy providers (T212, Web3) are removed; only Alpaca is supported.
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
        logger.info("BrokerageService: Initialized with ALPACA provider (T212/Web3 removed).")

    def test_connection(self) -> bool:
        return self.provider.test_connection()

    def get_venue(self, ticker: str) -> str:
        return self.provider_name

    def _format_ticker(self, ticker: str) -> str:
        return str(ticker or "").strip().upper()

    async def _pre_submit_gate(self, *, intent: str = "open") -> Optional[Dict[str, Any]]:
        """Fail-closed checks before any broker submit (F-002 bypass, F-004).

        ``intent=\"close\"`` skips capital-halt so exits remain available when
        daily/drawdown halt is engaged. Opens/manual buys always check halt.
        """
        intent_norm = (intent or "open").strip().lower()
        if intent_norm not in {"open", "close", "manual"}:
            intent_norm = "open"

        # Shadow paper must never place broker opens (wallet/invest already guard;
        # this is the last line of defense).
        if settings.PAPER_TRADING and intent_norm != "close":
            return {
                "status": "error",
                "message": "broker submit blocked: PAPER_TRADING (shadow) mode",
            }

        # F-004: re-assert LIVE_CAPITAL_DANGER on every non-shadow submit.
        if not settings.PAPER_TRADING and not settings.LIVE_CAPITAL_DANGER:
            return {
                "status": "error",
                "message": "broker submit blocked: LIVE_CAPITAL_DANGER is false",
            }

        if intent_norm == "close":
            return None

        try:
            from src.services.capital_halt_service import enforce_capital_halt_or_raise_state
            from src.services.persistence_service import persistence_service
            from src.services.performance_service import performance_service

            halt = await enforce_capital_halt_or_raise_state(
                persistence_service=persistence_service,
                performance_service=performance_service,
                notification_service=None,
            )
            if halt.get("halt"):
                return {
                    "status": "error",
                    "message": f"capital_halt:{halt.get('reason')}",
                    "halt_reason": halt.get("reason"),
                    "halt_details": halt.get("details"),
                }
        except Exception as exc:  # noqa: BLE001
            logger.error("Broker pre-submit capital halt check failed open-fail-closed: %s", exc)
            return {
                "status": "error",
                "message": "capital_halt_check_failed",
            }
        return None

    async def place_market_order(
        self,
        ticker: str,
        quantity: float,
        side: str,
        limit_price: float = None,
        client_order_id: str = None,
        *,
        intent: str = "open",
    ) -> Dict[str, Any]:
        blocked = await self._pre_submit_gate(intent=intent)
        if blocked:
            blocked["venue"] = self.provider_name
            return blocked
        result = await self.provider.place_market_order(
            ticker, quantity, side, limit_price, client_order_id
        )
        result["venue"] = self.provider_name
        return result

    async def place_value_order(
        self,
        ticker: str,
        amount: float,
        side: str,
        price: float = None,
        client_order_id: str = None,
        *,
        intent: str = "open",
    ) -> Dict[str, Any]:
        blocked = await self._pre_submit_gate(intent=intent)
        if blocked:
            blocked["venue"] = self.provider_name
            return blocked
        result = await self.provider.place_value_order(
            ticker, amount, side, price, client_order_id
        )
        result["venue"] = self.provider_name
        status = str(result.get("status", "")).lower()
        # F-018: Alpaca returns "success" on accept — accrue budget on submit, not only "filled".
        billable = status in {"filled", "success"} and not result.get("requires_reconciliation")
        if billable and not settings.PAPER_TRADING and intent != "close":
            filled_amount = result.get("filled_notional") or result.get("filled_amount") or amount
            try:
                budget_amount = float(filled_amount)
            except (TypeError, ValueError):
                budget_amount = amount
            if side.upper() == "BUY":
                budget_service.update_used_budget(self.provider_name, budget_amount)
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
        """
        Retrieve the available tradable quantity for a given ticker from the account's positions.
        
        Matches a position whose `ticker` equals the provided `ticker` or starts with it. Uses the position's `quantityAvailableForTrading` when present, otherwise falls back to `quantity`. Returns 0.0 if no matching position is found.
        
        Parameters:
            ticker (str): The normalized ticker to look up; providers are expected to return normalized `ticker` values.
        
        Returns:
            float: Available quantity for trading for the matched ticker, or 0.0 if none.
        """
        def _matches_symbol(position_symbol: str, requested: str) -> bool:
            sym = str(position_symbol or "").upper()
            req = str(requested or "").upper()
            if not sym or not req:
                return False
            if sym == req:
                return True
            # Handle broker-formatted tickers such as "AAPL_US_EQ",
            # "NASDAQ:AAPL", or provider payloads with suffixes.
            compact = sym.replace("NASDAQ:", "").replace("NYSE:", "")
            if compact == req or compact.startswith(f"{req}_") or compact.startswith(f"{req}."):
                return True
            return sym.startswith(req)

        def _matches_symbol(position_symbol: str, requested: str) -> bool:
            sym = str(position_symbol or "").upper()
            req = str(requested or "").upper()
            if not sym or not req:
                return False
            if sym == req:
                return True
            # Handle broker-formatted tickers such as "AAPL_US_EQ",
            # "NASDAQ:AAPL", or provider payloads with suffixes.
            compact = sym.replace("NASDAQ:", "").replace("NYSE:", "")
            if compact == req or compact.startswith(f"{req}_") or compact.startswith(f"{req}."):
                return True
            return sym.startswith(req)

        positions = await self.get_positions(ticker)
        for pos in positions:
            pos_ticker = (
                pos.get("ticker")
                or pos.get("symbol")
                or pos.get("instrumentTicker")
                or pos.get("instrument")
                or ""
            )
            if _matches_symbol(pos_ticker, ticker):
                qty = (
                    pos.get("quantityAvailableForTrading")
                    or pos.get("availableQuantity")
                    or pos.get("tradableQuantity")
                    or pos.get("quantity")
                    or pos.get("qty")
                    or 0.0
                )
                return float(qty or 0.0)
            pos_ticker = (
                pos.get("ticker")
                or pos.get("symbol")
                or pos.get("instrumentTicker")
                or pos.get("instrument")
                or ""
            )
            if _matches_symbol(pos_ticker, ticker):
                qty = (
                    pos.get("quantityAvailableForTrading")
                    or pos.get("availableQuantity")
                    or pos.get("tradableQuantity")
                    or pos.get("quantity")
                    or pos.get("qty")
                    or 0.0
                )
                return float(qty or 0.0)
        return 0.0

    async def get_pending_orders(self) -> List[Dict[str, Any]]:
        data = await asyncio.to_thread(self.provider.get_pending_orders)
        return AwaitableList(data)

    async def has_pending_order(self, ticker: str) -> bool:
        orders = await self.get_pending_orders()
        return any(o.get('ticker') == ticker for o in orders)

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        if hasattr(self.provider, "get_order"):
            return await self.provider.get_order(order_id)
        return {}

    async def get_order_by_client_order_id(self, client_order_id: str) -> Dict[str, Any]:
        getter = getattr(self.provider, "get_order_by_client_order_id", None)
        if getter is None:
            raise AttributeError(
                f"{type(self.provider).__name__} does not support get_order_by_client_order_id"
            )
        return await getter(client_order_id)

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
        if not orders:
            return AwaitableFloat(0.0)

        # First pass: identify orders missing a limit price and collect their tickers
        tickers_to_fetch = []
        for order in orders:
            try:
                notional = float(order.get('notional') or 0.0)
            except (TypeError, ValueError):
                notional = 0.0
            if notional > 0.0:
                continue

            try:
                price = float(order.get('limitPrice') or order.get('price') or 0.0)
            except (TypeError, ValueError):
                price = 0.0
            
            if price <= 0.0:
                ticker = order.get('ticker')
                if ticker:
                    tickers_to_fetch.append(ticker)

        # Batch fetch all missing prices in one call
        fetched_prices = {}
        if tickers_to_fetch:
            from src.services.data_service import data_service
            fetched_prices = await data_service.get_latest_price_async(tickers_to_fetch)

        # Second pass: calculate total value using batched prices where needed
        total_value = 0.0
        for order in orders:
            try:
                notional = float(order.get('notional') or 0.0)
            except (TypeError, ValueError):
                notional = 0.0
            if notional > 0.0:
                total_value += notional
                continue

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
                    ticker = order.get('ticker')
                    price = float(fetched_prices.get(ticker, 0.0) or 0.0)
                
                total_value += (qty * price)
        
        return AwaitableFloat(total_value)


class _LazyBrokerageService:
    def __init__(self):
        self._instance: Optional[BrokerageService] = None

    def _get_instance(self) -> BrokerageService:
        if self._instance is None:
            self._instance = BrokerageService()
        return self._instance

    def __getattr__(self, name):
        return getattr(self._get_instance(), name)

    @property
    def provider_name(self):
        return self._get_instance().provider_name

    @provider_name.setter
    def provider_name(self, value):
        self._get_instance().provider_name = value

    @property
    def provider(self):
        return self._get_instance().provider

    @provider.setter
    def provider(self, value):
        self._get_instance().provider = value

    def configure_provider(self, provider_name: str = None):
        return self._get_instance().configure_provider(provider_name)

    def test_connection(self) -> bool:
        return self._get_instance().test_connection()

    def get_venue(self, ticker: str) -> str:
        return self._get_instance().get_venue(ticker)

    def _format_ticker(self, ticker: str) -> str:
        return self._get_instance()._format_ticker(ticker)

    async def place_market_order(
        self,
        ticker: str,
        quantity: float,
        side: str,
        limit_price: float = None,
        client_order_id: str = None,
        *,
        intent: str = "open",
    ) -> Dict[str, Any]:
        return await self._get_instance().place_market_order(
            ticker,
            quantity,
            side,
            limit_price,
            client_order_id,
            intent=intent,
        )

    async def place_value_order(
        self,
        ticker: str,
        amount: float,
        side: str,
        price: float = None,
        client_order_id: str = None,
        *,
        intent: str = "open",
    ) -> Dict[str, Any]:
        return await self._get_instance().place_value_order(
            ticker,
            amount,
            side,
            price,
            client_order_id,
            intent=intent,
        )

    def get_symbol_metadata(self, ticker: str) -> Dict[str, Any]:
        return self._get_instance().get_symbol_metadata(ticker)

    async def is_asset_active(self, ticker: str) -> bool:
        return await self._get_instance().is_asset_active(ticker)

    async def get_portfolio(self) -> List[Dict[str, Any]]:
        return await self._get_instance().get_portfolio()

    async def get_positions(self, ticker: str = None) -> List[Dict[str, Any]]:
        return await self._get_instance().get_positions(ticker)

    async def get_available_quantity(self, ticker: str) -> float:
        return await self._get_instance().get_available_quantity(ticker)

    async def get_pending_orders(self) -> List[Dict[str, Any]]:
        return await self._get_instance().get_pending_orders()

    async def has_pending_order(self, ticker: str) -> bool:
        return await self._get_instance().has_pending_order(ticker)

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        return await self._get_instance().get_order(order_id)

    async def get_order_by_client_order_id(self, client_order_id: str) -> Dict[str, Any]:
        return await self._get_instance().get_order_by_client_order_id(client_order_id)

    async def is_ticker_owned(self, ticker: str) -> bool:
        return await self._get_instance().is_ticker_owned(ticker)

    async def get_account_cash(self) -> float:
        return await self._get_instance().get_account_cash()

    async def get_account_equity(self) -> float:
        return await self._get_instance().get_account_equity()

    async def get_account_buying_power(self) -> float:
        return await self._get_instance().get_account_buying_power()

    async def get_pending_orders_value(self) -> float:
        return await self._get_instance().get_pending_orders_value()


brokerage_service = _LazyBrokerageService()
