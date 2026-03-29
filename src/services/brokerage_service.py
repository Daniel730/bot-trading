import requests
import logging
from typing import List, Dict, Any
from src.config import settings

logger = logging.getLogger(__name__)

class BrokerageService:
    def __init__(self):
        self.base_url = "https://demo.trading212.com/api/v1" if settings.is_t212_demo else "https://live.trading212.com/api/v1"
        self.headers = {
            "Authorization": settings.effective_t212_key
        }

    def test_connection(self) -> bool:
        """Tests connectivity using account info endpoints."""
        endpoints = ["/equity/account/info", "/account/info"]
        for ep in endpoints:
            try:
                response = requests.get(f"{self.base_url}{ep}", headers=self.headers)
                if response.status_code == 200:
                    logger.info(f"T212: Connection successful via {ep}")
                    return True
            except:
                continue
        return False

    def get_portfolio(self) -> List[Dict[str, Any]]:
        """Fetch current holdings."""
        endpoints = ["/equity/portfolio", "/portfolio", "/cfd/portfolio"]
        for ep in endpoints:
            try:
                response = requests.get(f"{self.base_url}{ep}", headers=self.headers)
                if response.status_code == 200:
                    return response.json()
            except:
                continue
        return []

    def place_market_order(self, ticker: str, quantity: float, side: str) -> Dict[str, Any]:
        """Place a market order with CFD fallback."""
        # For CFD, some tickers don't use suffixes or use different ones
        endpoints = ["/equity/orders/market", "/orders/market", "/cfd/orders/market"]
        payload = {"symbol": ticker, "quantity": quantity, "side": side}
        
        for ep in endpoints:
            url = f"{self.base_url}{ep}"
            try:
                response = requests.post(url, headers=self.headers, json=payload)
                if response.status_code == 200:
                    return response.json()
                logger.warning(f"T212: {ep} failed ({response.status_code}): {response.text}")
            except Exception as e:
                continue
        
        return {"status": "error", "message": "All order endpoints failed"}
