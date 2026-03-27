import requests
import time
import logging
from src.config import T212_API_KEY, T212_API_SECRET
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class BrokerageService:
    def __init__(self, demo: bool = True):
        self.base_url = "https://demo.trading212.com" if demo else "https://live.trading212.com"
        self.auth = (T212_API_KEY, T212_API_SECRET)
        self.last_order_time = 0
        self.rate_limit_seconds = 2

    def _wait_for_rate_limit(self):
        elapsed = time.time() - self.last_order_time
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)

    def create_market_order(self, ticker: str, quantity: float) -> Dict[str, Any]:
        """
        Creates a market order on Trading 212.
        Quantity is positive for BUY, negative for SELL.
        """
        self._wait_for_rate_limit()
        
        endpoint = f"{self.base_url}/api/v0/equity/orders/market"
        payload = {
            "ticker": ticker,
            "quantity": quantity,
            "extendedHours": False # Principle I
        }
        
        response = requests.post(endpoint, json=payload, auth=self.auth)
        self.last_order_time = time.time()
        
        if response.status_code == 201:
            logger.info(f"Market order created for {ticker}: {quantity}")
            return response.json()
        else:
            logger.error(f"Failed to create market order for {ticker}: {response.text}")
            response.raise_for_status()

    def fetch_portfolio(self) -> List[Dict[str, Any]]:
        """
        Fetches current positions from Trading 212.
        Used for startup quantity re-syncing.
        """
        endpoint = f"{self.base_url}/api/v0/equity/portfolio"
        response = requests.get(endpoint, auth=self.auth)
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to fetch portfolio: {response.text}")
            response.raise_for_status()

    def get_cash_balance(self) -> float:
        """
        Fetches the free cash balance.
        """
        endpoint = f"{self.base_url}/api/v0/equity/account/cash"
        response = requests.get(endpoint, auth=self.auth)
        
        if response.status_code == 200:
            return response.json().get("free", 0.0)
        else:
            logger.error(f"Failed to fetch cash balance: {response.text}")
            response.raise_for_status()
