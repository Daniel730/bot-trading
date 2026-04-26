import asyncio
import time
import uuid
from typing import List, Dict, Any
from src.config import settings
from src.services.web3_service import web3_service
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import requests
import logging
import base64
from decimal import Decimal

logger = logging.getLogger(__name__)

class BrokerageService:
    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key or settings.effective_t212_key.strip()
        self.api_secret = api_secret or settings.T212_API_SECRET.strip()
        self.web3 = web3_service
        self._cache = {}
        self._cache_ttl = 5  # 5 seconds
        self._cache_lock = asyncio.Lock()  # FR-014: Single-Flight prevention (Async)

        # In-memory cache for API endpoints
        self._metadata_cache = {}
        self._metadata_last_fetch = 0
        self._METADATA_TTL_SECONDS = 86400  # 24 hours

        # V0 is the standard for the current public beta API
        self.base_url = "https://demo.trading212.com/api/v0" if settings.is_t212_demo else "https://live.trading212.com/api/v0"

        self.session = requests.Session()

        # FR-016: Key Sanitization & Verification
        if self.api_key:
            auth_key_len = len(self.api_key)
            secret_len = len(self.api_secret) if self.api_secret else 0

            # Update session headers
            self.session.headers.update(self.headers)

            masked_key = f"{self.api_key[:4]}...{self.api_key[-4:]}" if auth_key_len > 8 else "****"
            logger.info(f"T212 Service Initialized. Auth: {'BASIC (Key+Secret)' if secret_len > 0 else 'DIRECT (Key Only)'} | KeyLen: {auth_key_len} | SecretLen: {secret_len} | Mode: {'DEMO' if settings.is_t212_demo else 'LIVE'}")
        else:
            logger.error("T212 ERROR: No API Key found in settings.")
            self.session.headers.update({"Content-Type": "application/json"})

    @property
    def headers(self) -> Dict[str, str]:
        """Constructs the correct header based on available credentials."""
        headers = {"Content-Type": "application/json"}

        if self.api_key and self.api_secret:
            # Standard Basic Auth for T212
            creds = f"{self.api_key}:{self.api_secret}"
            encoded = base64.b64encode(creds.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        elif self.api_key:
            # Fallback to direct key if no secret
            headers["Authorization"] = self.api_key

        return headers

    def test_connection(self) -> bool:
        """Tests v0 endpoints with direct authorization."""
        # Note: equity/account/cash is a reliable endpoint for testing connectivity in v0
        endpoints = ["/equity/account/cash", "/equity/portfolio"]

        for ep in endpoints:
            url = f"{self.base_url}{ep}"
            try:
                logger.info(f"T212: Probing {url}...")
                response = requests.get(url, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    logger.info(f"T212: SUCCESS! Connected via {url}")
                    return True
                logger.warning(f"T212: {url} rejected with {response.status_code}")
            except Exception as e:
                logger.error(f"T212: Error connecting to {url}: {e}")
        return False

    def _format_ticker(self, ticker: str) -> str:
        """
        Maps Yahoo Finance style tickers to Trading 212 IDs.
        Examples:
        - AAPL -> AAPL_US_EQ
        - BTCE.DE -> BTCE_DE_EQ
        - AIR.PA -> AIR_PA_EQ
        """
        if "_" in ticker:
            return ticker  # Already formatted

        if ticker.endswith(".DE"):
            return ticker.replace(".DE", "_DE_EQ")
        if ticker.endswith(".PA"):
            return ticker.replace(".PA", "_PA_EQ")
        if ticker.endswith(".L"):
            return ticker.replace(".L", "_L_EQ")

        return f"{ticker}_US_EQ"

    @staticmethod
    def _is_crypto_ticker(ticker: str) -> bool:
        return "-USD" in ticker.upper()

    async def place_market_order(self, ticker: str, quantity: float, side: str, limit_price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        # P-03: Method is now async so _recover_timeout_order can be awaited correctly
        t212_ticker = self._format_ticker(ticker)

        # Bug M-13: Tick Size & Increment Validation using Decimal
        metadata = self.get_symbol_metadata(ticker)
        qty_incr = Decimal(str(metadata.get("quantityIncrement", "0.000001")))
        tick_size = Decimal(str(metadata.get("tickSize", "0.01")))

        # T212 v0 Market Order: Positive quantity for BUY, Negative for SELL
        decimal_qty = Decimal(str(quantity))
        final_qty_dec = (decimal_qty / qty_incr).quantize(Decimal("1"), rounding="ROUND_HALF_UP") * qty_incr
        final_qty = float(final_qty_dec)

        if side.upper() == "SELL":
            final_qty = -abs(final_qty)
        else:
            final_qty = abs(final_qty)

        # H-01: Accept caller-provided idempotency key so retries reuse the same ID.
        # Callers must generate the UUID once before any retry loop and pass it here.
        if not client_order_id:
            client_order_id = str(uuid.uuid4())

        payload = {
            "ticker": t212_ticker,
            "quantity": final_qty,
            "clientOrderId": client_order_id
        }

        # Feature 018: Add slippage guard (limitPrice) if provided
        if limit_price:
            # Bug M-13: Limit Price Tick Size
            decimal_limit = Decimal(str(limit_price))
            rounded_limit = (decimal_limit / tick_size).quantize(Decimal("1"), rounding="ROUND_HALF_UP") * tick_size
            payload["limitPrice"] = float(rounded_limit)
            url = f"{self.base_url}/equity/orders/limit"
            logger.info(f"T212: Executing LIMIT {side} for {t212_ticker} (Qty: {final_qty}, Limit: {payload['limitPrice']}, ID: {client_order_id[:8]})")
        else:
            url = f"{self.base_url}/equity/orders/market"
            logger.info(f"T212: Executing MARKET {side} for {t212_ticker} (Qty: {final_qty}, ID: {client_order_id[:8]})")

        try:
            # P-03: Use asyncio.to_thread so the blocking requests.post doesn't stall the event loop
            response = await asyncio.to_thread(
                requests.post, url, headers=self.headers, json=payload, timeout=15
            )
            if response.status_code == 200:
                logger.info(f"T212: Order SUCCESS (ID: {client_order_id[:8]})")
                return response.json()

            logger.warning(f"T212: Order failed ({response.status_code}): {response.text}")
            return {"status": "error", "message": response.text}
        except requests.exceptions.Timeout:
            logger.error(f"T212: Timeout placing order {client_order_id}. Checking status...")
            return await self._recover_timeout_order(client_order_id, ticker)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _recover_timeout_order(self, client_order_id: str, ticker: str) -> Dict[str, Any]:
        """Polls for the order status after a timeout to prevent duplicates."""
        await asyncio.sleep(2)  # Give broker a moment to process
        orders = await self.get_pending_orders()
        for o in orders:
            if o.get('clientOrderId') == client_order_id:
                logger.info(f"T212: Recovered timed-out order {client_order_id[:8]} - Found in PENDING.")
                return o

        # Check history if it filled instantly
        # (Hypothetical logic for history search)
        return {"status": "timeout", "message": "Order status unknown after timeout. Check dashboard."}

    async def execute_order(self, ticker: str, amount_fiat: float, side: str = "buy") -> Dict[str, Any]:
        """
        Executes a value-based order, primarily for DCA and goal-oriented investing.
        """
        return await self.place_value_order(ticker, amount_fiat, side)

    async def check_dividends_and_reinvest(self):
        """
        Feature 015 (FR-004) / Feature 018 (FR-005): Fetches account activity to identify dividends and reinvests them.
        Safety: Execution value capped at min(gross_dividend, available_free_cash).
        """
        logger.info("T212: Checking for new dividends to reinvest (DRIP)...")

        url = f"{self.base_url}/history/transactions"
        try:
            start_timestamp = int((time.time() - (48 * 3600)) * 1000)
            # B-05: Wrap sync requests.Session.get in to_thread to avoid blocking the event loop
            response = await asyncio.to_thread(
                self.session.get, url,
                headers=self.session.headers,
                params={"from": start_timestamp}
            )

            if response.status_code != 200:
                return False

            transactions = response.json()

            for tx in transactions:
                if tx.get('type') == 'DIVIDEND' and tx.get('amount', 0) > 0:
                    # Bug H-03: Re-fetch available cash fresh before each leg
                    available_cash = await asyncio.to_thread(self.get_account_cash)
                    if available_cash is None:
                        logger.warning("DRIP: Account cash unavailable. Skipping leg.")
                        continue

                    ticker = tx.get('ticker')
                    dividend_amount = float(tx.get('amount'))

                    # Feature 018 Safety Cap
                    execution_value = min(dividend_amount, available_cash)

                    if execution_value < 1.0:  # Minimum $1 trade size for fractional
                        logger.info(f"DRIP: Skipping {ticker} (Value ${execution_value:.2f} < $1.00)")
                        continue

                    logger.info(f"DRIP: Reinvesting ${execution_value:.2f} into {ticker} (Dividend: ${dividend_amount:.2f}, Cash: ${available_cash:.2f})")
                    res = await self.place_value_order(ticker, execution_value, "BUY")
        except Exception as e:
            logger.error(f"DRIP: Error during reinvestment sweep: {e}")
            return False

        return True

    async def place_value_order(self, ticker: str, amount: float, side: str) -> Dict[str, Any]:
        # Feature 037: route crypto spot orders to on-chain Web3 execution
        # while keeping all non-crypto tickers on Trading212.
        if self._is_crypto_ticker(ticker) and not settings.PAPER_TRADING:
            logger.info("BrokerageDispatcher: routing %s to Web3 service", ticker)
            return await self.web3.place_value_order(ticker=ticker, amount=amount, side=side)
        return await self._place_value_order_t212(ticker=ticker, amount=amount, side=side)

    async def _place_value_order_t212(self, ticker: str, amount: float, side: str) -> Dict[str, Any]:
        """
        Feature 014/016: Executes a value-based order by calculating required quantity.
        Enforces minTradeQuantity and quantityIncrement from brokerage metadata.
        """
        from src.services.data_service import data_service
        from src.services.risk_service import risk_service
        from src.services.agent_log_service import agent_logger

        # 1. Friction analysis before execution
        friction_res = risk_service.calculate_friction(amount, ticker=ticker)
        if not friction_res["is_acceptable"]:
            return {"status": "error", "message": friction_res["rejection_reason"]}
        friction = friction_res["friction_pct"]

        # 2. Price and Quantity calculation
        # Bug M-05: Added await to async price fetch
        prices = await data_service.get_latest_price([ticker])
        if ticker not in prices:
            return {"status": "error", "message": f"Could not retrieve latest price for {ticker}"}

        price = prices[ticker]
        raw_quantity = amount / price

        # 3. Metadata validation
        metadata = self.get_symbol_metadata(ticker)
        min_qty = float(metadata.get("minTradeQuantity", 0.0))
        qty_incr = float(metadata.get("quantityIncrement", 1e-6))

        if min_qty > 0 and raw_quantity < min_qty:
            return {
                "status": "error",
                "message": f"Quantity {raw_quantity:.6f} below minTradeQuantity {min_qty} for {ticker}"
            }

        final_quantity = raw_quantity
        if qty_incr > 0:
            final_quantity = round(raw_quantity / qty_incr) * qty_incr
            final_quantity = float(round(final_quantity, 6))

        logger.info(f"T212: Value order {ticker}: ${amount} / ${price:.2f} = {final_quantity:.6f} shares")

        # Feature 018: Calculate 1% slippage-capped limitPrice
        limit_price = price * 1.01 if side.upper() == "BUY" else price * 0.99

        # P-04 (2026-04-26): place_market_order is async — must be awaited.
        # Previously this created an un-awaited coroutine, so live orders were
        # silently dropped and result.get("status") would raise AttributeError.
        result = await self.place_market_order(ticker, final_quantity, side, limit_price=limit_price)

        if result.get("status") != "error":
            agent_logger.log_fractional_trade(ticker, amount, final_quantity, price, side, friction)

        return result

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True
    )
    def get_symbol_metadata(self, ticker: str) -> Dict[str, Any]:
        """Retrieves metadata for a specific symbol, using an internal 24-hour cache to avoid 429 errors."""
        t212_ticker = self._format_ticker(ticker)

        now = time.time()
        # Se cache for valido e existir o ticker
        if (now - self._metadata_last_fetch) < self._METADATA_TTL_SECONDS and t212_ticker in self._metadata_cache:
            return self._metadata_cache[t212_ticker]

        url = f"{self.base_url}/instruments"
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                instruments = response.json()
                # Atualizar todo o cache
                self._metadata_cache = {inst.get('ticker'): inst for inst in instruments}
                self._metadata_last_fetch = now

                return self._metadata_cache.get(t212_ticker, {})
            elif response.status_code == 401:
                logger.error(f"T212 Auth Error (401) on {url}: {response.text}")
                raise requests.exceptions.HTTPError("401 Unauthorized")
            else:
                logger.error(f"T212 Metadata Error: {response.status_code} - {response.text}")
                return {}
        except Exception as e:
            if isinstance(e, requests.exceptions.HTTPError):
                raise
            logger.error(f"Error fetching metadata for {ticker}: {e}")
            return {}

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True
    )
    async def get_portfolio(self) -> List[Dict[str, Any]]:
        cache_key = "portfolio"
        async with self._cache_lock:
            now = time.time()
            if cache_key in self._cache:
                data, timestamp = self._cache[cache_key]
                if now - timestamp < self._cache_ttl:
                    return data

            url = f"{self.base_url}/equity/portfolio"
            try:
                # M-11: offload blocking HTTP call so the event loop stays free while lock is held
                response = await asyncio.to_thread(self.session.get, url, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    self._cache[cache_key] = (data, now)
                    return data
                elif response.status_code == 401:
                    logger.error(f"T212 Auth Error (401) on {url}: {response.text}")
                    raise requests.exceptions.HTTPError("401 Unauthorized")
            except:
                raise
            return []

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True
    )
    async def get_pending_orders(self) -> List[Dict[str, Any]]:
        """Retrieves a list of all active/pending orders."""
        cache_key = "orders"
        async with self._cache_lock:
            now = time.time()
            if cache_key in self._cache:
                data, timestamp = self._cache[cache_key]
                if now - timestamp < self._cache_ttl:
                    return data

            url = f"{self.base_url}/equity/orders"
            try:
                # M-11: offload blocking HTTP call so the event loop stays free while lock is held
                response = await asyncio.to_thread(self.session.get, url, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    orders = response.json()
                    self._cache[cache_key] = (orders, now)
                    if orders:
                        logger.info(f"T212: Found {len(orders)} pending orders.")
                    return orders
                elif response.status_code == 401:
                    logger.error(f"T212 Auth Error (401) on {url}: {response.text}")
                    raise requests.exceptions.HTTPError("401 Unauthorized")
                else:
                    logger.warning(f"T212: Failed to fetch orders ({response.status_code}): {response.text}")
            except Exception as e:
                if isinstance(e, requests.exceptions.HTTPError):
                    raise
                logger.error(f"T212: Error fetching orders: {e}")
            return []

    async def has_pending_order(self, ticker: str) -> bool:
        """Checks if there is already a pending order for the given ticker."""
        orders = await self.get_pending_orders()
        t212_ticker = self._format_ticker(ticker)
        return any(o.get('ticker') == t212_ticker for o in orders)

    async def is_ticker_owned(self, ticker: str) -> bool:
        """Checks if the account currently holds the given ticker."""
        portfolio = await self.get_portfolio()
        t212_ticker = self._format_ticker(ticker)
        return any(pos.get('ticker') == t212_ticker for pos in portfolio)

    async def get_pending_orders_value(self) -> float:
        """Calculates the total cash currently committed to pending BUY orders."""
        orders = await self.get_pending_orders()
        total_value = 0.0
        for order in orders:
            qty = order.get('quantity', 0.0)
            if qty > 0:
                price = order.get('limitPrice') or order.get('stopPrice') or order.get('price', 0.0)

                if price == 0 and 'ticker' in order:
                    logger.warning(f"T212: Pending order for {order['ticker']} has 0 price. Attempting fallback...")
                    from src.services.data_service import data_service
                    fallback_prices = await data_service.get_latest_price([order['ticker']])
                    price = fallback_prices.get(order['ticker'], 0.0)
                    if price > 0:
                        logger.info(f"T212: Fallback price for {order['ticker']} found: ${price:.2f}")
                    else:
                        logger.error(f"T212: Critical failure - fallback price also 0.0 for {order['ticker']}")

                total_value += (qty * price)

        if total_value > 0:
            logger.info(f"T212: Total commitment calculated: ${total_value:.2f}")
        return total_value

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True
    )
    def get_account_cash(self) -> float:
        """Retrieves free funds from the account. T212 only exposes v0 — the
        previous v1 fallback always 404'd and just spammed the log. We now hit
        v0 only and treat 429 as a soft, transient failure (None) so the caller
        can use a fallback balance instead of crashing the scan loop."""
        url = f"{self.base_url}/equity/account/cash"
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                return float(response.json().get('free', 0.0))
            if response.status_code == 401:
                logger.warning(f"T212 Auth Failure on {url}. Data: {response.text}")
                raise requests.exceptions.HTTPError(f"401 Unauthorized on {url}")
            if response.status_code == 429:
                # Rate-limited — caller will use a fallback. Logged at debug
                # level on purpose: this happens often when the dashboard polls.
                logger.debug(f"T212 cash endpoint rate-limited (429): {url}")
                return None
            logger.warning(f"T212 Endpoint {url} returned {response.status_code}")
        except requests.exceptions.HTTPError:
            raise
        except Exception as e:
            logger.error(f"T212 Request error on {url}: {e}")
        return None

brokerage_service = BrokerageService()
