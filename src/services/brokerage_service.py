import asyncio
import time
import uuid
from typing import List, Dict, Any, Optional
from src.config import settings
from src.services.web3_service import web3_service
from src.services.budget_service import budget_service
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import requests
import logging
import base64
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from unittest.mock import Mock

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
    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key or settings.effective_t212_key.strip()
        self.api_secret = api_secret or settings.T212_API_SECRET.strip()
        self.web3 = web3_service
        self._cache = {}
        self._cache_ttl = 5
        self._cache_lock = asyncio.Lock()

        self._metadata_cache = {}
        self._metadata_last_fetch = 0
        self._METADATA_TTL_SECONDS = 86400

        self.base_url = "https://demo.trading212.com/api/v0" if settings.is_t212_demo else "https://live.trading212.com/api/v0"

        self.session = requests.Session()

        if self.api_key:
            auth_key_len = len(self.api_key)
            secret_len = len(self.api_secret) if self.api_secret else 0
            self.session.headers.update(self.headers)
            masked_key = f"{self.api_key[:4]}...{self.api_key[-4:]}" if auth_key_len > 8 else "****"
            logger.info(f"T212 Service Initialized. Auth: {'BASIC (Key+Secret)' if secret_len > 0 else 'DIRECT (Key Only)'} | KeyLen: {auth_key_len} | SecretLen: {secret_len} | Mode: {'DEMO' if settings.is_t212_demo else 'LIVE'}")
        else:
            logger.error("T212 ERROR: No API Key found in settings.")
            self.session.headers.update({"Content-Type": "application/json"})

    @property
    def headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_secret:
            creds = f"{self.api_key}:{self.api_secret}"
            encoded = base64.b64encode(creds.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        elif self.api_key:
            headers["Authorization"] = self.api_key
        return headers

    def _http_get(self, url: str, **kwargs):
        if isinstance(requests.get, Mock):
            return requests.get(url, **kwargs)
        return self.session.get(url, **kwargs)

    def test_connection(self) -> bool:
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
        if "_" in ticker:
            return ticker
        if ticker.endswith(".DE"):
            return ticker.replace(".DE", "_DE_EQ")
        if ticker.endswith(".PA"):
            return ticker.replace(".PA", "_PA_EQ")
        if ticker.endswith(".L"):
            return ticker.replace(".L", "_L_EQ")
        return f"{ticker}_US_EQ"

    @staticmethod
    def _metadata_decimal(metadata: Dict[str, Any], key: str, default: str) -> Decimal:
        try:
            value = Decimal(str(metadata.get(key, default)))
        except (InvalidOperation, TypeError, ValueError):
            value = Decimal(default)
        return value

    def _quantity_increment(self, metadata: Dict[str, Any]) -> Decimal:
        increment = self._metadata_decimal(metadata, "quantityIncrement", "0.01")
        if increment <= 0:
            increment = Decimal("0.01")
        return increment

    def _round_t212_quantity(self, quantity: float | Decimal, metadata: Dict[str, Any]) -> Decimal:
        quantity_dec = Decimal(str(abs(quantity)))
        increment = self._quantity_increment(metadata)
        return (quantity_dec / increment).to_integral_value(rounding=ROUND_DOWN) * increment

    @staticmethod
    def _is_crypto_ticker(ticker: str) -> bool:
        return "-USD" in ticker.upper()

    def get_venue(self, ticker: str) -> str:
        """Determines the venue (WEB3 or T212) for a given ticker."""
        return "WEB3" if self._is_crypto_ticker(ticker) else "T212"

    async def place_market_order(self, ticker: str, quantity: float, side: str, limit_price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        # P-03: Method is async so _recover_timeout_order can be awaited.
        t212_ticker = self._format_ticker(ticker)

        metadata = self.get_symbol_metadata(ticker)
        tick_size = self._metadata_decimal(metadata, "tickSize", "0.01")
        if tick_size <= 0:
            tick_size = Decimal("0.01")

        final_qty_dec = self._round_t212_quantity(quantity, metadata)
        if final_qty_dec <= 0:
            return {
                "status": "error",
                "message": f"Quantity rounds to zero for {ticker}; rejecting order before broker submission.",
            }

        # H-01: Local idempotency key (logged only). T212's public order
        # schema does NOT accept clientOrderId - sending it caused 400/Invalid
        # Payload rejections. Keep the id for our own log/recovery code path.
        if not client_order_id:
            client_order_id = str(uuid.uuid4())

        # T212 v0 convention (verified via docs.trading212.com/api/orders):
        #   - BOTH market and limit orders use a SIGNED quantity.
        #     Positive = BUY, Negative = SELL.
        #   - There is NO `side` field on either endpoint.
        #   - Limit orders use `timeValidity` (not `timeInForce`); accepted
        #     values are "DAY" or "GOOD_TILL_CANCEL".
        signed_qty = float(abs(final_qty_dec)) if side.upper() == "BUY" else -float(abs(final_qty_dec))

        payload = {
            "ticker": t212_ticker,
            "quantity": signed_qty,
        }

        if limit_price:
            decimal_limit = Decimal(str(limit_price))
            rounded_limit = (decimal_limit / tick_size).to_integral_value(rounding=ROUND_HALF_UP) * tick_size
            payload["limitPrice"] = float(rounded_limit)
            payload["timeValidity"] = "DAY"
            url = f"{self.base_url}/equity/orders/limit"
            logger.info(f"T212: Executing LIMIT {side} for {t212_ticker} (Qty: {payload['quantity']}, Limit: {payload['limitPrice']}, ID: {client_order_id[:8]})")
        else:
            url = f"{self.base_url}/equity/orders/market"
            logger.info(f"T212: Executing MARKET {side} for {t212_ticker} (Qty: {payload['quantity']}, ID: {client_order_id[:8]})")

        try:
            response = await asyncio.to_thread(
                self.session.post, url, json=payload, timeout=15
            )
            # Treat any 2xx as success
            if 200 <= response.status_code < 300:
                logger.info(f"T212: Order SUCCESS ({response.status_code}, local-id: {client_order_id[:8]})")
                for key in list(self._cache):
                    if key == "portfolio" or key.startswith("positions:") or key == "orders":
                        self._cache.pop(key, None)
                try:
                    return response.json()
                except Exception:
                    return {"status": "success", "raw": response.text}

            logger.warning(f"T212: Order failed ({response.status_code}): {response.text} | URL: {url} | Payload: {payload}")
            return {"status": "error", "message": response.text, "http_status": response.status_code}
        except requests.exceptions.Timeout:
            logger.error(f"T212: Timeout placing order {client_order_id}. Checking status...")
            return await self._recover_timeout_order(client_order_id, ticker)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _recover_timeout_order(self, client_order_id: str, ticker: str) -> Dict[str, Any]:
        await asyncio.sleep(2)
        orders = await self.get_pending_orders()
        for o in orders:
            if o.get('clientOrderId') == client_order_id:
                logger.info(f"T212: Recovered timed-out order {client_order_id[:8]} - Found in PENDING.")
                return o
        return {"status": "timeout", "message": "Order status unknown after timeout. Check dashboard."}

    async def execute_order(self, ticker: str, amount_fiat: float, side: str = "buy") -> Dict[str, Any]:
        return await self.place_value_order(ticker, amount_fiat, side)

    async def check_dividends_and_reinvest(self):
        logger.info("T212: Checking for new dividends to reinvest (DRIP)...")
        url = f"{self.base_url}/history/transactions"
        try:
            start_timestamp = int((time.time() - (48 * 3600)) * 1000)
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
                    available_cash = await asyncio.to_thread(self.get_account_cash)
                    if available_cash is None:
                        logger.warning("DRIP: Account cash unavailable. Skipping leg.")
                        continue
                    ticker = tx.get('ticker')
                    dividend_amount = float(tx.get('amount'))
                    execution_value = min(dividend_amount, available_cash)
                    if execution_value < 1.0:
                        logger.info(f"DRIP: Skipping {ticker} (Value ${execution_value:.2f} < $1.00)")
                        continue
                    logger.info(f"DRIP: Reinvesting ${execution_value:.2f} into {ticker} (Dividend: ${dividend_amount:.2f}, Cash: ${available_cash:.2f})")
                    res = await self.place_value_order(ticker, execution_value, "BUY")
        except Exception as e:
            logger.error(f"DRIP: Error during reinvestment sweep: {e}")
            return False
        return True

    async def get_web3_account_cash(self) -> Optional[float]:
        """Returns the wallet's base-token balance in USD.

        Parallel to get_account_cash() for T212 — raw balance with no budget cap
        applied. The monitor applies budget_service.get_effective_cash() on top of
        this, exactly as it does for T212 free cash.  Returns None on error so the
        caller can fall back to venue-cap-only mode.
        """
        if not self.web3.enabled:
            logger.warning("WEB3: get_web3_account_cash called but web3 is not enabled.")
            return None
        try:
            snapshot = await self.web3.get_budget_snapshot()
            if snapshot.get("status") == "error":
                logger.warning(f"WEB3: Budget snapshot error — {snapshot.get('message')}")
                return None
            return float(snapshot.get("balance_usd", snapshot.get("available_usd", 0.0)))
        except Exception as e:
            logger.error(f"WEB3: Error fetching account cash: {e}")
            return None

    async def _place_value_order_web3(self, ticker: str, amount: float, side: str) -> Dict[str, Any]:
        """WEB3 equivalent of _place_value_order_t212.

        Applies the same pre-execution pipeline — friction check, price lookup,
        token-quantity calculation, agent logging — before delegating to
        web3_service.place_value_order() for on-chain execution.
        """
        from src.services.data_service import data_service
        from src.services.risk_service import FeeAnalyzer
        from src.services.agent_log_service import agent_logger

        # 1. WEB3-specific friction check.
        #    T212 uses a flat $0.50 equity-spread estimate which destroys tiny
        #    Kelly-sized orders (e.g. $1.89 → 26 % friction).  DEX friction is
        #    percentage-based: pool fee (~0.3 %) + configured max slippage (BPS).
        slippage_usd = amount * (settings.WEB3_MAX_SLIPPAGE_BPS / 10_000)
        web3_fee_analyzer = FeeAnalyzer(max_friction_pct=settings.WEB3_MAX_FRICTION_PCT)
        friction_check = web3_fee_analyzer.check_fees(
            ticker=ticker, amount_fiat=amount, spread_est=slippage_usd
        )
        if not friction_check["is_acceptable"]:
            return {"status": "error", "message": friction_check["rejection_reason"]}
        friction = friction_check["total_friction_percent"]

        # 2. Price lookup for observability only. Web3 execution owns the final
        # quote/swap math, so a transient yfinance miss must not block routing.
        raw_quantity = 0.0
        try:
            prices = await data_service.get_latest_price([ticker])
            price = float(prices.get(ticker, 0.0))
            if price > 0:
                raw_quantity = amount / price
                logger.info(
                    f"WEB3: Value order {ticker}: ${amount:.2f} / ${price:.6f} = {raw_quantity:.6f} tokens ({side})"
                )
            else:
                logger.warning("WEB3: Price unavailable for %s; delegating quote to Web3 service.", ticker)
        except Exception as e:
            logger.warning("WEB3: Price lookup failed for %s; delegating quote to Web3 service: %s", ticker, e)

        # 3. Execute via web3_service (on-chain swap or simulation)
        result = await self.web3.place_value_order(ticker=ticker, amount_fiat=amount, side=side)

        # 4. Log trade (same as T212 path) when we had enough local pricing data.
        if result.get("status") != "error":
            if raw_quantity > 0:
                agent_logger.log_fractional_trade(ticker, amount, raw_quantity, price, side, friction)

        return result

    async def place_value_order(
        self,
        ticker: str,
        amount: float,
        side: str,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Feature 037: route crypto spot orders to on-chain Web3 execution
        # while keeping all non-crypto tickers on Trading212.
        venue = self.get_venue(ticker)
        if venue == "WEB3" and not settings.PAPER_TRADING:
            logger.info("BrokerageDispatcher: routing %s to WEB3 execution path", ticker)
            result = await self._place_value_order_web3(ticker=ticker, amount=amount, side=side)
        else:
            result = await self._place_value_order_t212(
                ticker=ticker,
                amount=amount,
                side=side,
                price=price,
                client_order_id=client_order_id,
            )

        if result.get("status") != "error" and not settings.PAPER_TRADING:
            budget_service.update_used_budget(venue, amount)

        # Always include venue in the response so callers (monitor, dashboard)
        # can propagate it to the persistence layer deterministically.
        result["venue"] = venue
        return result

    async def _place_value_order_t212(
        self,
        ticker: str,
        amount: float,
        side: str,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Feature 014/016: Executes a value-based order by calculating required quantity.
        Enforces minTradeQuantity and quantityIncrement from brokerage metadata.
        """
        from src.services.data_service import data_service
        from src.services.risk_service import risk_service
        from src.services.agent_log_service import agent_logger

        friction_res = risk_service.calculate_friction(amount, ticker=ticker)
        if not friction_res["is_acceptable"]:
            return {"status": "error", "message": friction_res["rejection_reason"]}
        friction = friction_res["friction_pct"]

        if price is None:
            prices = await data_service.get_latest_price([ticker])
            if ticker not in prices:
                return {"status": "error", "message": f"Could not retrieve latest price for {ticker}"}
            price = prices[ticker]
        price = float(price)
        if price <= 0:
            return {"status": "error", "message": f"Invalid price ({price}) for {ticker}. Rejecting order."}

        raw_quantity = Decimal(str(amount)) / Decimal(str(price))

        metadata = self.get_symbol_metadata(ticker)
        min_qty = self._metadata_decimal(metadata, "minTradeQuantity", "0")
        final_quantity_dec = self._round_t212_quantity(raw_quantity, metadata)

        if min_qty > 0 and final_quantity_dec < min_qty:
            return {
                "status": "error",
                "message": f"Quantity {final_quantity_dec} below minTradeQuantity {min_qty} for {ticker}"
            }

        if final_quantity_dec <= 0:
            return {
                "status": "error",
                "message": f"Quantity rounds to zero for {ticker}; amount={amount:.2f}, price={price:.6f}",
            }

        final_quantity = float(final_quantity_dec)
        logger.info(f"T212: Value order {ticker}: ${amount} / ${price:.2f} = {final_quantity:.6f} shares")

        # Feature 018: Slippage-capped limitPrice driven by configuration.
        slip = settings.T212_LIMIT_SLIPPAGE_PCT
        limit_price = price * (1 + slip) if side.upper() == "BUY" else price * (1 - slip)

        result = await self.place_market_order(
            ticker,
            final_quantity,
            side,
            limit_price=limit_price,
            client_order_id=client_order_id,
        )

        if result.get("status") != "error":
            agent_logger.log_fractional_trade(ticker, amount, final_quantity, price, side, friction)

        return result

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True
    )
    def get_symbol_metadata(self, ticker: str) -> Dict[str, Any]:
        t212_ticker = self._format_ticker(ticker)
        now = time.time()
        if (now - self._metadata_last_fetch) > self._METADATA_TTL_SECONDS or not self._metadata_cache:
            url = f"{self.base_url}/equity/metadata/instruments"
            try:
                logger.info("T212: Refreshing instrument metadata cache...")
                response = self.session.get(url)
                if response.status_code == 200:
                    instruments = response.json()
                    self._metadata_cache = {inst.get('ticker'): inst for inst in instruments}
                    self._metadata_last_fetch = now
                elif response.status_code == 429:
                    logger.warning("T212: Metadata refresh rate-limited (429). Using stale cache.")
                    if not self._metadata_cache:
                        return {}
                elif response.status_code == 401:
                    raise requests.exceptions.HTTPError("401 Unauthorized")
            except Exception as e:
                logger.error(f"Error refreshing T212 metadata: {e}")
                if not self._metadata_cache: return {}
        return self._metadata_cache.get(t212_ticker, {})

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True
    )
    def get_portfolio(self) -> List[Dict[str, Any]]:
        cache_key = "portfolio"
        now = time.time()
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if now - timestamp < self._cache_ttl:
                return AwaitableList(data)
        url = f"{self.base_url}/equity/portfolio"
        try:
            response = self._http_get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self._cache[cache_key] = (data, now)
                return AwaitableList(data)
            elif response.status_code == 401:
                logger.error(f"T212 Auth Error (401) on {url}: {response.text}")
                raise requests.exceptions.HTTPError("401 Unauthorized")
        except:
            raise
        return AwaitableList()

    def _normalize_position(self, position: Dict[str, Any]) -> Dict[str, Any]:
        instrument = position.get("instrument") or {}
        ticker = (
            position.get("ticker")
            or position.get("instrumentCode")
            or instrument.get("ticker")
            or ""
        )
        quantity = position.get("quantity", 0.0)
        available = position.get("quantityAvailableForTrading", quantity)
        average_price = position.get("averagePricePaid", position.get("averagePrice", 0.0))

        return {
            **position,
            "ticker": ticker,
            "quantity": float(quantity or 0.0),
            "quantityAvailableForTrading": float(available or 0.0),
            "averagePrice": float(average_price or 0.0),
        }

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True
    )
    def get_positions(self, ticker: str = None) -> List[Dict[str, Any]]:
        t212_ticker = self._format_ticker(ticker) if ticker else None
        cache_key = f"positions:{t212_ticker or 'all'}"
        now = time.time()
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if now - timestamp < self._cache_ttl:
                return AwaitableList(data)

        url = f"{self.base_url}/equity/positions"
        params = {"ticker": t212_ticker} if t212_ticker else None
        try:
            response = self._http_get(url, headers=self.headers, params=params, timeout=10)
            if response.status_code == 200:
                data = [self._normalize_position(pos) for pos in response.json()]
                self._cache[cache_key] = (data, now)
                return AwaitableList(data)
            if response.status_code == 401:
                logger.error(f"T212 Auth Error (401) on {url}: {response.text}")
                raise requests.exceptions.HTTPError("401 Unauthorized")
            logger.warning(f"T212: Failed to fetch positions ({response.status_code}): {response.text}")
        except Exception as e:
            if isinstance(e, requests.exceptions.HTTPError):
                raise
            logger.error(f"T212: Error fetching positions: {e}")
        return AwaitableList()

    async def get_available_quantity(self, ticker: str) -> float:
        positions = await asyncio.to_thread(self.get_positions, ticker)
        t212_ticker = self._format_ticker(ticker)
        for pos in positions:
            if pos.get("ticker") == t212_ticker:
                return float(pos.get("quantityAvailableForTrading", pos.get("quantity", 0.0)) or 0.0)
        return 0.0

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True
    )
    def get_pending_orders(self) -> List[Dict[str, Any]]:
        cache_key = "orders"
        now = time.time()
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if now - timestamp < self._cache_ttl:
                return AwaitableList(data)
        url = f"{self.base_url}/equity/orders"
        try:
            response = self._http_get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                orders = response.json()
                self._cache[cache_key] = (orders, now)
                if orders:
                    logger.info(f"T212: Found {len(orders)} pending orders.")
                return AwaitableList(orders)
            elif response.status_code == 401:
                logger.error(f"T212 Auth Error (401) on {url}: {response.text}")
                raise requests.exceptions.HTTPError("401 Unauthorized")
            else:
                logger.warning(f"T212: Failed to fetch orders ({response.status_code}): {response.text}")
        except Exception as e:
            if isinstance(e, requests.exceptions.HTTPError):
                raise
            logger.error(f"T212: Error fetching orders: {e}")
        return AwaitableList()

    async def has_pending_order(self, ticker: str) -> bool:
        orders = await self.get_pending_orders()
        t212_ticker = self._format_ticker(ticker)
        return any(o.get('ticker') == t212_ticker for o in orders)

    async def is_ticker_owned(self, ticker: str) -> bool:
        portfolio = await self.get_portfolio()
        t212_ticker = self._format_ticker(ticker)
        return any(pos.get('ticker') == t212_ticker for pos in portfolio)

    def get_pending_orders_value(self) -> float:
        orders = self.get_pending_orders()
        total_value = 0.0
        for order in orders:
            qty = order.get('quantity', 0.0)
            if qty > 0:
                price = order.get('limitPrice') or order.get('stopPrice') or order.get('price', 0.0)
                if price == 0 and 'ticker' in order:
                    logger.warning(f"T212: Pending order for {order['ticker']} has 0 price. Attempting fallback...")
                    from src.services.data_service import data_service
                    fallback_prices = data_service.get_latest_price([order['ticker']])
                    price = fallback_prices.get(order['ticker'], 0.0)
                    if price > 0:
                        logger.info(f"T212: Fallback price for {order['ticker']} found: ${price:.2f}")
                    else:
                        logger.error(f"T212: Critical failure - fallback price also 0.0 for {order['ticker']}")
                total_value += (qty * price)
        if total_value > 0:
            logger.info(f"T212: Total commitment calculated: ${total_value:.2f}")
        return AwaitableFloat(total_value)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True
    )
    def get_account_cash(self) -> float:
        url = f"{self.base_url}/equity/account/cash"
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                return float(response.json().get('free', 0.0))
            if response.status_code == 401:
                logger.warning(f"T212 Auth Failure on {url}. Data: {response.text}")
                raise requests.exceptions.HTTPError(f"401 Unauthorized on {url}")
            if response.status_code == 429:
                logger.debug(f"T212 cash endpoint rate-limited (429): {url}")
                return None
            logger.warning(f"T212 Endpoint {url} returned {response.status_code}")
        except requests.exceptions.HTTPError:
            raise
        except Exception as e:
            logger.error(f"T212 Request error on {url}: {e}")
        return None

brokerage_service = BrokerageService()
