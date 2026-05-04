import asyncio
import logging
import alpaca_trade_api as tradeapi
import re
from typing import List, Dict, Any, Optional
from src.config import settings
from src.services.brokerage.base import AbstractBrokerageProvider

logger = logging.getLogger(__name__)

class AlpacaProvider(AbstractBrokerageProvider):
    _US_SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")
    _CRYPTO_PAIR_PATTERN = re.compile(r"^[A-Z0-9]{2,15}/[A-Z]{3,4}$")
    _CRYPTO_DASH_PAIR_PATTERN = re.compile(r"^[A-Z0-9]{2,15}-[A-Z]{3,4}$")
    _active_symbols_cache: Optional[set] = None
    _active_symbols_last_fetch: float = 0

    @classmethod
    def normalize_symbol(cls, ticker: str) -> str:
        """
        Normalize a ticker to Alpaca's share-class format and uppercase form.

        Parameters:
            ticker (str): The input ticker symbol; may be None or empty.

        Returns:
            str: The normalized ticker symbol. Converts "LEFT-RIGHT" to "LEFT.RIGHT" when both sides are alphabetic and the right side length is <= 2; otherwise returns the trimmed, uppercased input (or an empty string).
        """
        symbol = (ticker or "").strip().upper()
        if cls._CRYPTO_DASH_PAIR_PATTERN.fullmatch(symbol):
            base, quote = symbol.rsplit("-", 1)
            return f"{base}/{quote}"
        # Alpaca uses BRK.B style share-class symbols.
        if "-" in symbol and "." not in symbol:
            left, right = symbol.rsplit("-", 1)
            if left.isalpha() and right.isalpha() and len(right) <= 2:
                return f"{left}.{right}"
        return symbol

    @classmethod
    def is_crypto_symbol(cls, ticker: str) -> bool:
        return bool(cls._CRYPTO_PAIR_PATTERN.fullmatch(cls.normalize_symbol(ticker)))

    @classmethod
    def is_supported_symbol(cls, ticker: str) -> bool:
        """
        Determines whether a ticker is a supported US-format symbol after normalization.

        Parameters:
            ticker (str): Ticker string to validate; it will be normalized before checking.

        Returns:
            True if the normalized ticker matches the provider's US symbol pattern, False otherwise.
        """
        symbol = cls.normalize_symbol(ticker)
        return bool(cls._US_SYMBOL_PATTERN.fullmatch(symbol) or cls._CRYPTO_PAIR_PATTERN.fullmatch(symbol))

    @classmethod
    def to_bot_symbol(cls, symbol: str) -> str:
        normalized = cls.normalize_symbol(symbol)
        if cls._CRYPTO_PAIR_PATTERN.fullmatch(normalized):
            return normalized.replace("/", "-")
        return normalized

    @classmethod
    def order_time_in_force(cls, ticker: str) -> str:
        return "gtc" if cls.is_crypto_symbol(ticker) else "day"

    def __init__(self, api_key: str = None, api_secret: str = None, base_url: str = None):
        """
        Configure the provider with Alpaca credentials and create the Alpaca REST client.

        Parameters:
            api_key (str, optional): Alpaca API key; if omitted, loaded from settings.ALPACA_API_KEY and stripped of surrounding whitespace.
            api_secret (str, optional): Alpaca API secret; if omitted, loaded from settings.ALPACA_API_SECRET and stripped of surrounding whitespace.
            base_url (str, optional): Alpaca base URL; if omitted, loaded from settings.ALPACA_BASE_URL and stripped of surrounding whitespace.

        Notes:
            Sets instance attributes for the credentials and instantiates `self.api` as an `alpaca_trade_api.REST` client (api_version='v2').
        """
        self.api_key = api_key or settings.ALPACA_API_KEY.strip()
        self.api_secret = api_secret or settings.ALPACA_API_SECRET.strip()
        self.base_url = base_url or settings.ALPACA_BASE_URL.strip()

        self.api = tradeapi.REST(
            self.api_key,
            self.api_secret,
            self.base_url,
            api_version='v2'
        )

    def test_connection(self) -> bool:
        """
        Check whether the configured Alpaca account can be retrieved using the current API credentials and endpoint.

        Returns:
            bool: True if the account was successfully retrieved from Alpaca, False otherwise.
        """
        try:
            self.api.get_account()
            # Refresh active symbols cache on connection test
            self._get_active_symbols()
            return True
        except Exception as e:
            logger.error(f"Alpaca connection failed: {e}")
            return False

    def _get_active_symbols(self) -> set:
        """Fetch and cache the set of active symbols from Alpaca."""
        import time
        now = time.time()
        # Cache for 1 hour
        if self._active_symbols_cache is None or now - self._active_symbols_last_fetch > 3600:
            try:
                # Fetch only active US equities and Crypto to reduce payload and avoid plan-limit errors
                equity_assets = self.api.list_assets(status='active', asset_class='us_equity')
                crypto_assets = self.api.list_assets(status='active', asset_class='crypto')
                self._active_symbols_cache = {a.symbol for a in equity_assets} | {a.symbol for a in crypto_assets}
                self._active_symbols_last_fetch = now
                logger.info(f"AlpacaProvider: Cached {len(self._active_symbols_cache)} active symbols")
            except Exception as e:
                logger.error(f"AlpacaProvider: Failed to fetch active assets: {e}")
                if self._active_symbols_cache is None:
                    return set()
        return self._active_symbols_cache

    async def is_asset_active(self, ticker: str) -> bool:
        """Check if a ticker is currently active and tradable on Alpaca."""
        symbol = self.normalize_symbol(ticker)
        active_set = await asyncio.to_thread(self._get_active_symbols)
        return symbol in active_set

    async def place_market_order(self, ticker: str, quantity: float, side: str, limit_price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        """
        Place a market or limit order for the given ticker on Alpaca.

        Validates the ticker is supported and submits either a market order (when no limit_price) or a limit order (when limit_price is provided). The function returns a standardized result dictionary indicating success or error.

        Parameters:
            ticker (str): Symbol to trade; will be normalized and validated for Alpaca.
            quantity (float): Quantity to buy or sell.
            side (str): Order side, e.g., "buy" or "sell" (case-insensitive).
            limit_price (float, optional): If provided, a limit order is submitted at this price.
            client_order_id (str, optional): Optional client-generated identifier to attach to the order.

        Returns:
            dict: On success: {"status": "success", "order_id": <broker id>, "broker": "ALPACA", "client_order_id": <client id or None>}.
                  On failure: {"status": "error", "message": <human-readable error message>}.
        """
        if not self.is_supported_symbol(ticker):
            return {"status": "error", "message": f"Ticker {ticker} is not supported by Alpaca"}

        broker_symbol = self.normalize_symbol(ticker)
        if not await self.is_asset_active(ticker):
            logger.error(f"Alpaca: {broker_symbol} is currently inactive/non-tradable")
            return {"status": "error", "message": f"Asset {broker_symbol} is not active on Alpaca"}
        try:
            order_type = 'limit' if limit_price else 'market'
            params = {
                'symbol': broker_symbol,
                'qty': quantity,
                'side': side.lower(),
                'type': order_type,
                'time_in_force': self.order_time_in_force(ticker)
            }
            if limit_price:
                params['limit_price'] = limit_price
            if client_order_id:
                params['client_order_id'] = client_order_id

            order = await asyncio.to_thread(self.api.submit_order, **params)
            return {
                "status": "success",
                "order_id": order.id,
                "broker": "ALPACA",
                "client_order_id": order.client_order_id
            }
        except Exception as e:
            logger.error(f"Alpaca order failed for {broker_symbol}: {e}")
            return {"status": "error", "message": str(e)}

    async def place_value_order(self, ticker: str, amount: float, side: str, price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        """
        Place a notional (value-based) market order for a ticker, falling back to a quantity-based market order when notional submission fails.

        Attempts to submit a market order using the provided notional `amount`. If the broker rejects notional orders for the asset, falls back to computing a quantity from `price` (or the latest market price if `price` is omitted) and submits a quantity-based market order.

        Parameters:
            ticker (str): Symbol to trade.
            amount (float): Notional value in account currency to allocate to the order.
            side (str): Order side, e.g., 'buy' or 'sell'.
            price (float, optional): Price to use for fallback quantity calculation; if omitted, the latest price will be fetched.
            client_order_id (str, optional): Client-provided identifier to attach to the order.

        Returns:
            dict: On success: {"status": "success", "order_id": <broker order id>, "broker": "ALPACA", "client_order_id": <client id or None>}. On error: {"status": "error", "message": <error message>}.
        """
        if not self.is_supported_symbol(ticker):
            return {"status": "error", "message": f"Ticker {ticker} is not supported by Alpaca"}

        broker_symbol = self.normalize_symbol(ticker)
        if not await self.is_asset_active(ticker):
            logger.error(f"Alpaca: {broker_symbol} is currently inactive/non-tradable (value order)")
            return {"status": "error", "message": f"Asset {broker_symbol} is not active on Alpaca"}
        side_normalized = side.lower()
        if side_normalized == "sell":
            return await self._place_quantity_from_notional(
                ticker,
                amount,
                side,
                price=price,
                client_order_id=client_order_id,
            )
        try:
            # Alpaca supports notional orders (value-based) natively for many assets
            # Notional value must be limited to 2 decimal places.
            rounded_amount = round(float(amount), 2)
            params = {
                'symbol': broker_symbol,
                'notional': rounded_amount,
                'side': side_normalized,
                'type': 'market',
                'time_in_force': self.order_time_in_force(ticker)
            }
            if client_order_id:
                params['client_order_id'] = client_order_id

            order = await asyncio.to_thread(self.api.submit_order, **params)
            return {
                "status": "success",
                "order_id": order.id,
                "broker": "ALPACA",
                "client_order_id": order.client_order_id
            }
        except Exception as e:
            logger.warning(f"Alpaca notional order failed for {broker_symbol}, falling back to quantity: {e}")
            # Fallback to calculating quantity if notional is not supported for this asset
            from src.services.data_service import data_service
            if price is None:
                prices = await data_service.get_latest_price_async([ticker])
                price = prices.get(ticker)

            if not price or price <= 0:
                return {"status": "error", "message": f"Invalid price for {ticker} fallback"}

            quantity = round(float(amount) / float(price), 6)
            return await self.place_market_order(ticker, quantity, side, client_order_id=client_order_id)

    async def _place_quantity_from_notional(
        self,
        ticker: str,
        amount: float,
        side: str,
        *,
        price: float = None,
        client_order_id: str = None,
    ) -> Dict[str, Any]:
        from src.services.data_service import data_service

        if price is None:
            prices = await data_service.get_latest_price_async([ticker])
            price = prices.get(ticker)

        if not price or price <= 0:
            return {"status": "error", "message": f"Invalid price for {ticker} quantity order"}

        quantity = round(float(amount) / float(price), 6)
        if quantity <= 0:
            return {"status": "error", "message": f"Amount {amount} rounds to zero quantity for {ticker}"}
        return await self.place_market_order(
            ticker,
            quantity,
            side,
            client_order_id=client_order_id,
        )

    def get_portfolio(self) -> List[Dict[str, Any]]:
        """
        Retrieve the account's current portfolio as a list of normalized position records.

        Returns:
            List[Dict[str, Any]]: Normalized position dictionaries for each open position. Returns an empty list if the portfolio cannot be retrieved.
        """
        try:
            positions = self.api.list_positions()
            return [self._normalize_position(p) for p in positions]
        except Exception as e:
            logger.error(f"Alpaca failed to fetch portfolio: {e}")
            return []

    def get_positions(self, ticker: str = None) -> List[Dict[str, Any]]:
        """
        Retrieve current positions from the brokerage; returns either all positions or the position for a single ticker.

        Parameters:
            ticker (str, optional): Ticker symbol to fetch. If provided, returns a single-item list with the normalized position for that ticker, or an empty list if the position is not found.

        Returns:
            List[Dict[str, Any]]: A list of normalized position dictionaries. Returns an empty list if no positions are available or if an error occurs.
        """
        try:
            if ticker:
                broker_symbol = self.normalize_symbol(ticker)
                try:
                    p = self.api.get_position(broker_symbol)
                    return [self._normalize_position(p)]
                except:
                    return []
            positions = self.api.list_positions()
            return [self._normalize_position(p) for p in positions]
        except Exception as e:
            logger.error(f"Alpaca failed to fetch positions: {e}")
            return []

    def get_account_cash(self) -> float:
        """
        Retrieve the account cash balance from the connected Alpaca account.

        Returns:
            float: The account cash balance. Returns 0.0 if the balance cannot be fetched.
        """
        try:
            account = self.api.get_account()
            return float(account.cash)
        except Exception as e:
            logger.error(f"Alpaca failed to fetch account cash: {e}")
            return 0.0

    def get_account_equity(self) -> float:
        """
        Retrieve the total account equity (cash + position value) from Alpaca.

        Returns:
            float: Total account equity. Returns 0.0 if the balance cannot be fetched.
        """
        try:
            account = self.api.get_account()
            return float(account.equity)
        except Exception as e:
            logger.error(f"Alpaca failed to fetch account equity: {e}")
            return 0.0

    def get_account_buying_power(self) -> float:
        """
        Retrieve the available buying power from Alpaca.

        Returns:
            float: Available buying power. Returns 0.0 if the balance cannot be fetched.
        """
        try:
            account = self.api.get_account()
            return float(account.buying_power)
        except Exception as e:
            logger.error(f"Alpaca failed to fetch account buying power: {e}")
            return 0.0

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """
        Fetch open orders from Alpaca and return them in normalized dictionary form.

        Returns:
            List[Dict[str, Any]]: A list of normalized order dictionaries (keys include `ticker`, `quantity`, `side`, `status`, `limitPrice`, `id`). Returns an empty list if fetching orders fails.
        """
        try:
            orders = self.api.list_orders(status='open')
            return [self._normalize_order(o) for o in orders]
        except Exception as e:
            logger.error(f"Alpaca failed to fetch pending orders: {e}")
            return []

    def get_symbol_metadata(self, ticker: str) -> Dict[str, Any]:
        """
        Retrieve normalized metadata for a tradable symbol from Alpaca.

        Parameters:
            ticker (str): Asset symbol to query.

        Returns:
            dict: Metadata with keys:
                - ticker: asset symbol.
                - minTradeQuantity: minimum tradable quantity (0.0001 for fractionable assets, 1.0 otherwise).
                - quantityIncrement: smallest tradable quantity increment (0.0001 for fractionable assets, 1.0 otherwise).
                - tickSize: minimum price increment (0.01).
                - status: asset status string.
            Returns an empty dict if metadata cannot be retrieved.
        """
        if not self.is_supported_symbol(ticker):
            return {}
        try:
            asset = self.api.get_asset(self.normalize_symbol(ticker))
            return {
                "ticker": self.to_bot_symbol(asset.symbol),
                "minTradeQuantity": 0.0001 if asset.fractionable else 1.0,
                "quantityIncrement": 0.0001 if asset.fractionable else 1.0,
                "tickSize": 0.01,
                "status": asset.status
            }
        except Exception as e:
            logger.error(f"Alpaca failed to fetch metadata for {ticker}: {e}")
            return {}

    def _normalize_position(self, p) -> Dict[str, Any]:
        """
        Normalize an Alpaca position object into a standardized dictionary.

        Parameters:
            p: An Alpaca position-like object providing attributes `symbol`, `qty`, `avg_entry_price`, `current_price`, and `market_value`. May optionally provide `qty_available`.

        Returns:
            dict: A normalized position with the following keys:
                - ticker (str): Position symbol.
                - quantity (float): Total quantity held.
                - quantityAvailableForTrading (float): Quantity available for trading (uses `qty_available` when present, otherwise `qty`).
                - averagePrice (float): Average entry price.
                - currentPrice (float): Current market price.
                - marketValue (float): Market value of the position.
        """
        return {
            "ticker": self.to_bot_symbol(p.symbol),
            "quantity": float(p.qty),
            "quantityAvailableForTrading": float(p.qty_available) if hasattr(p, 'qty_available') else float(p.qty),
            "averagePrice": float(p.avg_entry_price),
            "currentPrice": float(p.current_price),
            "marketValue": float(p.market_value)
        }

    def _normalize_order(self, o) -> Dict[str, Any]:
        """
        Convert an Alpaca order object into a normalized dictionary.

        Parameters:
            o: Alpaca order object returned by the Alpaca REST client.

        Returns:
            dict: Normalized order with keys:
                - ticker (str): Order symbol.
                - quantity (float): Quantity as a float; 0.0 if missing or falsy.
                - side (str): Order side in uppercase (e.g., "BUY", "SELL").
                - status (str): Order status from Alpaca.
                - limitPrice (float | None): Limit price as a float, or None if not set.
                - id (str): Broker order identifier.
        """
        return {
            "ticker": self.to_bot_symbol(o.symbol),
            "quantity": float(o.qty) if o.qty else 0.0,
            "side": o.side.upper(),
            "status": o.status,
            "limitPrice": float(o.limit_price) if o.limit_price else None,
            "id": o.id
        }
