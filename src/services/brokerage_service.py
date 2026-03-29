import requests
import time
import logging
import base64
from src.config import T212_API_KEY, T212_API_SECRET
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class BrokerageService:
    def __init__(self, demo: bool = True):
        # Using the official Beta API endpoints if they differ, otherwise keeping these
        self.base_url = "https://demo.trading212.com" if demo else "https://live.trading212.com"
        
        # Basic Auth header construction
        auth_str = f"{T212_API_KEY}:{T212_API_SECRET}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        self.headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/json"
        }
        
        self.last_order_time = 0
        self.rate_limit_seconds = 12  # Strict 5 req/min (60/5 = 12s) for free tier compliance

    def _wait_for_rate_limit(self):
        elapsed = time.time() - self.last_order_time
        if elapsed < self.rate_limit_seconds:
            sleep_time = self.rate_limit_seconds - elapsed
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def place_market_order(self, ticker: str, quantity: float) -> Dict[str, Any]:
        """
        Creates a market order on Trading 212 Beta API.
        Quantity is positive for BUY, negative for SELL.
        """
        self._wait_for_rate_limit()
        
        endpoint = f"{self.base_url}/api/v0/equity/orders/market"
        # The API might expect absolute quantity and a separate action, 
        # but the contract in contracts.md says quantity can be negative.
        # We'll stick to the contract.
        payload = {
            "ticker": ticker,
            "quantity": quantity,
            "extendedHours": False
        }
        
        response = requests.post(endpoint, json=payload, headers=self.headers)
        self.last_order_time = time.time()
        
        if response.status_code in [200, 201]:
            logger.info(f"Market order successful for {ticker}: {quantity}")
            return response.json()
        else:
            logger.error(f"Failed to create market order for {ticker}: {response.text}")
            response.raise_for_status()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def fetch_positions(self) -> List[Dict[str, Any]]:
        """
        Fetches current positions (Portfolio).
        """
        endpoint = f"{self.base_url}/api/v0/equity/portfolio"
        response = requests.get(endpoint, headers=self.headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to fetch portfolio: {response.text}")
            response.raise_for_status()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def get_cash_balance(self) -> float:
        """
        Fetches the free cash balance.
        """
        endpoint = f"{self.base_url}/api/v0/equity/account/cash"
        response = requests.get(endpoint, headers=self.headers)
        
        if response.status_code == 200:
            return response.json().get("free", 0.0)
        else:
            logger.error(f"Failed to fetch cash balance: {response.text}")
            response.raise_for_status()
