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
        async def _coro():
            return self
        return _coro().__await__()

class AwaitableFloat(float):
    def __await__(self):
        async def _coro():
            return float(self)
        return _coro().__await__()

class T212Provider(AbstractBrokerageProvider):
    def __init__(self, api_key: str = None, api_secret: str = None):
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
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_secret:
            creds = f"{self.api_key}:{self.api_secret}"
            encoded = base64.b64encode(creds.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        elif self.api_key:
            headers["Authorization"] = self.api_key
        return headers

    def _format_ticker(self, ticker: str) -> str:
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
        try:
            value = Decimal(str(metadata.get(key, default)))
        except (InvalidOperation, TypeError, ValueError):
            value = Decimal(default)
        return value

    def _round_t212_quantity(self, quantity: float | Decimal, metadata: Dict[str, Any]) -> Decimal:
        quantity_dec = Decimal(str(abs(quantity)))
        increment = self._metadata_decimal(metadata, "quantityIncrement", "0.01")
        if increment <= 0:
            increment = Decimal("0.01")
        return (quantity_dec / increment).to_integral_value(rounding=ROUND_DOWN) * increment

    def test_connection(self) -> bool:
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
        t212_ticker = self._format_ticker(ticker)
        metadata = self.get_symbol_metadata(ticker)
        final_qty_dec = self._round_t212_quantity(quantity, metadata)
        
        if final_qty_dec <= 0:
            return {"status": "error", "message": f"Quantity rounds to zero for {ticker}"}

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
        url = f"{self.base_url}/equity/portfolio"
        response = self.session.get(url, timeout=10)
        return response.json() if response.status_code == 200 else []

    def get_positions(self, ticker: str = None) -> List[Dict[str, Any]]:
        t212_ticker = self._format_ticker(ticker) if ticker else None
        url = f"{self.base_url}/equity/positions"
        params = {"ticker": t212_ticker} if t212_ticker else None
        response = self.session.get(url, params=params, timeout=10)
        return response.json() if response.status_code == 200 else []

    def get_account_cash(self) -> float:
        url = f"{self.base_url}/equity/account/cash"
        response = self.session.get(url, timeout=10)
        return float(response.json().get('free', 0.0)) if response.status_code == 200 else 0.0

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/equity/orders"
        response = self.session.get(url, timeout=10)
        return response.json() if response.status_code == 200 else []
