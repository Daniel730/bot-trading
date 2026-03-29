import requests
from typing import List, Dict, Any
from src.config import T212_API_KEY, T212_API_SECRET, T212_DEMO
from src.models.arbitrage_models import BrokerageError

class BrokerageService:
    def __init__(self):
        self.base_url = "https://demo.trading212.com/api/v0" if T212_DEMO else "https://live.trading212.com/api/v0"
        self.headers = {
            "Authorization": f"Basic {T212_API_KEY}:{T212_API_SECRET}"
        }

    def get_portfolio(self) -> List[Dict[str, Any]]:
        """Fetch current holdings from Trading 212."""
        try:
            response = requests.get(f"{self.base_url}/equity/portfolio", headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise BrokerageError(f"Failed to fetch portfolio: {e}")

    def place_market_order(self, ticker: str, quantity: float, order_type: str) -> Dict[str, Any]:
        """Place a market order on Trading 212."""
        # Note: In T212 Beta API, Sell is often a negative quantity or separate endpoint
        # For this implementation, we follow the contract in brokerage_api.md
        payload = {
            "ticker": ticker,
            "quantity": quantity if order_type == "BUY" else -quantity,
            "extendedHours": False
        }
        try:
            response = requests.post(f"{self.base_url}/equity/orders/market", headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise BrokerageError(f"Failed to place {order_type} order for {ticker}: {e}")

    def get_account_cash(self) -> float:
        """Fetch available cash in the account."""
        try:
            response = requests.get(f"{self.base_url}/equity/account/cash", headers=self.headers)
            response.raise_for_status()
            return response.json().get("free", 0.0)
        except requests.exceptions.RequestException as e:
            raise BrokerageError(f"Failed to fetch account cash: {e}")
