import asyncio
import time
import uuid
import base64
import requests
import logging
from typing import List, Dict, Any, Optional
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from tenacity import retry, wait_exponential, stop_after_attempt
from src.config import settings
from src.services.brokerage.base import AbstractBrokerageProvider

logger = logging.getLogger(__name__)

class AwaitableList(list):
    def __await__(self):
        """
        Allow awaiting the object so the await expression evaluates to this instance.
        
        When used in an `await` expression, the coroutine returns this object.
        
        Returns:
            The instance itself.
        """
        async def _coro():
            """
            Coroutine that returns the surrounding instance when awaited.
            
            Returns:
                self: the instance that defined this coroutine
            """
            return self
        return _coro().__await__()

class AwaitableFloat(float):
    def __await__(self):
        """
        Allow awaiting this object to produce its numeric value.
        
        Returns:
            float: The numeric value of this instance.
        """
        async def _coro():
            """
            Return the float value represented by the AwaitableFloat instance.
            
            Returns:
                float: The numeric value of the instance.
            """
            return float(self)
        return _coro().__await__()

class T212Provider(AbstractBrokerageProvider):
    def __init__(self, api_key: str = None, api_secret: str = None):
        """
        Configure the provider with Trading212 credentials, select the demo or live base URL, create a persistent HTTP session with provider headers, and initialize in-memory caches and TTLs.
        
        Parameters:
            api_key (str, optional): Trading212 API key; if None, loaded from application settings and stripped.
            api_secret (str, optional): Trading212 API secret; if None, loaded from application settings and stripped.
        """
        self.api_key = api_key or settings.effective_t212_key.strip()
        self.api_secret = api_secret or settings.T212_API_SECRET.strip()
        self._cache = {}
        self._cache_ttl = 5
        self._metadata_cache = {}
        self._metadata_last_fetch = 0
        self._METADATA_TTL_SECONDS = 86400
        self.base_url = "https://demo.trading212.com/api/v0" if settings.is_t212_demo else "https://live.trading212.com/api/v0"
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    @property
    def headers(self) -> Dict[str, str]:
        """
        Build HTTP headers for Trading212 API requests.
        
        Returns:
            headers (Dict[str, str]): Mapping of header names to values. Always contains `"Content-Type": "application/json"`. If both `api_key` and `api_secret` are configured, includes an `"Authorization"` header with HTTP Basic credentials; if only `api_key` is configured, includes an `"Authorization"` header with the raw API key.
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_secret:
            creds = f"{self.api_key}:{self.api_secret}"
            encoded = base64.b64encode(creds.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        elif self.api_key:
            headers["Authorization"] = self.api_key
        return headers

    def _format_ticker(self, ticker: str) -> str:
        """
        Convert a user-facing ticker into the Trading212 instrument ticker format.
        
        Parameters:
        	ticker (str): The input ticker symbol. May be empty, already formatted (contains '_'), or end with country-specific suffixes like '.DE', '.PA', or '.L'.
        
        Returns:
        	formatted_ticker (str): The Trading212-formatted ticker: returns an empty string for falsy input, returns the input unchanged if it contains an underscore, replaces suffixes as follows: '.DE' → '_DE_EQ', '.PA' → '_PA_EQ', '.L' → '_L_EQ', and appends '_US_EQ' for all other tickers.
        """
        if not ticker: return ""
        if "_" in ticker:
            return ticker
        if ticker.endswith(".DE"):
            return ticker.replace(".DE", "_DE_EQ")
        if ticker.endswith(".PA"):
            return ticker.replace(".PA", "_PA_EQ")
        if ticker.endswith(".L"):
            return ticker.replace(".L", "_L_EQ")
        return f"{ticker}_US_EQ"

    def _metadata_decimal(self, metadata: Dict[str, Any], key: str, default: str) -> Decimal:
        """
        Convert a metadata field to a Decimal, using a provided default if the value is missing or invalid.
        
        Parameters:
            metadata (Dict[str, Any]): Mapping containing instrument metadata.
            key (str): Key to retrieve from the metadata mapping.
            default (str): String representation of the decimal value to use when the metadata key is missing or cannot be converted.
        
        Returns:
            Decimal: Decimal parsed from metadata[key] if present and valid, otherwise Decimal(default).
        """
        try:
            value = Decimal(str(metadata.get(key, default)))
        except (InvalidOperation, TypeError, ValueError):
            value = Decimal(default)
        return value

    def _round_t212_quantity(self, quantity: float | Decimal, metadata: Dict[str, Any]) -> Decimal:
        """
        Round the requested quantity down to the instrument's quantityIncrement.
        
        Negative quantities are treated as their absolute value. If metadata lacks a valid
        `quantityIncrement`, a default of 0.01 is used.
        
        Parameters:
            quantity (float | Decimal): Requested quantity; negative values are converted to positive.
            metadata (Dict[str, Any]): Instrument metadata from which `quantityIncrement` is read.
        
        Returns:
            Decimal: The absolute quantity rounded down to the nearest multiple of the instrument's `quantityIncrement`.
        """
        quantity_dec = Decimal(str(abs(quantity)))
        increment = self._metadata_decimal(metadata, "quantityIncrement", "0.01")
        if increment <= 0:
            increment = Decimal("0.01")
        return (quantity_dec / increment).to_integral_value(rounding=ROUND_DOWN) * increment

    def test_connection(self) -> bool:
        """
        Check whether the Trading212 API is reachable by probing account endpoints.
        
        Network errors and non-200 responses are treated as failures and suppressed.
        
        Returns:
            `true` if at least one probed endpoint returns HTTP 200, `false` otherwise.
        """
        endpoints = ["/equity/account/cash", "/equity/portfolio"]
        for ep in endpoints:
            url = f"{self.base_url}{ep}"
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    return True
            except Exception:
                pass
        return False

    async def place_market_order(self, ticker: str, quantity: float, side: str, limit_price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        """
        Place a market or limit order for the given ticker on Trading212.
        
        Parameters:
            ticker (str): Instrument symbol in user format; will be converted to Trading212 format.
            quantity (float): Desired order quantity; will be rounded down to the instrument's allowed quantityIncrement.
            side (str): Order side; "BUY" results in a buy (positive quantity), any other value results in a sell (negative quantity).
            limit_price (float, optional): If provided, the order is submitted as a limit order using this price.
            client_order_id (str, optional): Client-supplied identifier (accepted but not included in the provider payload).
        
        Returns:
            dict: On success: {"status": "success", "order_id": <orderId or None>, "broker": "T212"}.
                  On error: {"status": "error", "message": <error description>}.
        """
        t212_ticker = self._format_ticker(ticker)
        metadata = self.get_symbol_metadata(ticker)
        final_qty_dec = self._round_t212_quantity(quantity, metadata)
        
        if final_qty_dec <= 0:
            return {"status": "error", "message": f"Quantity rounds to zero for {ticker}"}

        min_qty = self._metadata_decimal(metadata, "minTradeQuantity", "0.0")
        if final_qty_dec < min_qty:
            return {"status": "error", "message": f"Quantity {final_qty_dec} is below minTradeQuantity {min_qty} for {ticker}"}

        signed_qty = float(final_qty_dec) if side.upper() == "BUY" else -float(final_qty_dec)
        payload = {"ticker": t212_ticker, "quantity": signed_qty}
        
        url = f"{self.base_url}/equity/orders/limit" if limit_price else f"{self.base_url}/equity/orders/market"
        if limit_price:
            payload["limitPrice"] = float(limit_price)

        try:
            response = self.session.post(url, json=payload, timeout=10)
            if response.status_code in [200, 202]:
                return {"status": "success", "order_id": response.json().get("orderId"), "broker": "T212"}
            return {"status": "error", "message": response.text}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def place_value_order(self, ticker: str, amount: float, side: str, price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        """
        Place an order for a target monetary value by converting the amount to instrument quantity and submitting the corresponding order.
        
        If `price` is not provided, fetches the latest price for `ticker`; returns an error dict if the resolved price is missing or not greater than zero. Calculates quantity as `amount / price` and derives a slippage-adjusted limit price using `settings.T212_LIMIT_SLIPPAGE_PCT` (increases the price for BUY, decreases for other sides). Submits the resulting order and returns the submission result.
        
        Parameters:
            ticker (str): Instrument symbol to trade (format accepted by provider).
            amount (float): Monetary amount to allocate to the position.
            side (str): `"BUY"` or other value for sell side.
            price (float, optional): Unit price to use; if omitted, the latest market price is requested.
            client_order_id (str, optional): Client-provided identifier (accepted but not forwarded to the broker).
        
        Returns:
            dict: On success, contains broker-specific order details (e.g., `orderId` and `broker: "T212"`). On error, contains `status: "error"` and a `message` explaining the failure (for example, invalid price).
        """
        from src.services.data_service import data_service
        if price is None:
            prices = await data_service.get_latest_price_async([ticker])
            price = prices.get(ticker)
        
        if not price or price <= 0:
            return {"status": "error", "message": f"Invalid price for {ticker}"}

        quantity = amount / price
        metadata = self.get_symbol_metadata(ticker)
        slip = settings.T212_LIMIT_SLIPPAGE_PCT
        limit_price = price * (1 + slip) if side.upper() == "BUY" else price * (1 - slip)

        return await self.place_market_order(ticker, quantity, side, limit_price=limit_price, client_order_id=client_order_id)

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3), reraise=True)
    def get_symbol_metadata(self, ticker: str) -> Dict[str, Any]:
        """
        Retrieve Trading212 instrument metadata for a given ticker, using a cached instruments list refreshed when the cache is older than the provider's TTL.
        
        Parameters:
            ticker (str): Ticker in common form (e.g., "AAPL", "VOD.L", "BNP.PA"); will be normalized to Trading212's ticker format before lookup.
        
        Returns:
            Dict[str, Any]: Metadata for the normalized ticker if found, otherwise an empty dict.
        """
        t212_ticker = self._format_ticker(ticker)
        now = time.time()
        if (now - self._metadata_last_fetch) > self._METADATA_TTL_SECONDS or not self._metadata_cache:
            url = f"{self.base_url}/equity/metadata/instruments"
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                self._metadata_cache = {inst.get('ticker'): inst for inst in response.json()}
                self._metadata_last_fetch = now
        return self._metadata_cache.get(t212_ticker, {})

    def get_portfolio(self) -> List[Dict[str, Any]]:
        """
        Retrieve the current account portfolio from Trading212.
        
        Returns:
            List[Dict[str, Any]]: Portfolio items parsed from the response JSON, or an empty list if the request fails or returns a non-200 status.
        """
        url = f"{self.base_url}/equity/portfolio"
        response = self.session.get(url, timeout=10)
        return response.json() if response.status_code == 200 else []

    def get_positions(self, ticker: str = None) -> List[Dict[str, Any]]:
        """
        Retrieve current account positions, optionally filtered to a single instrument.
        
        If `ticker` is provided it will be formatted to Trading212's instrument ticker before requesting positions.
        
        Parameters:
        	ticker (str, optional): Instrument symbol to filter positions (can be in local/user format).
        
        Returns:
        	List[Dict[str, Any]]: A list of position objects returned by the broker; returns an empty list if the request did not succeed (non-200 status).
        """
        t212_ticker = self._format_ticker(ticker) if ticker else None
        url = f"{self.base_url}/equity/positions"
        params = {"ticker": t212_ticker} if t212_ticker else None
        response = self.session.get(url, params=params, timeout=10)
        return response.json() if response.status_code == 200 else []

    def get_account_cash(self) -> float:
        """
        Fetches the account's available cash balance from Trading212.
        
        Returns:
            The free cash balance as a float, or 0.0 if the request fails or the value is missing.
        """
        url = f"{self.base_url}/equity/account/cash"
        response = self.session.get(url, timeout=10)
        return float(response.json().get('free', 0.0)) if response.status_code == 200 else 0.0

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """
        Retrieve the list of pending orders from the brokerage.
        
        Returns:
            A list of order dictionaries parsed from the broker response JSON, or an empty list if the request fails or the broker returns a non-200 status.
        """
        url = f"{self.base_url}/equity/orders"
        response = self.session.get(url, timeout=10)
        return response.json() if response.status_code == 200 else []
