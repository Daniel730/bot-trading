import requests
import logging
from typing import List, Dict, Any
from src.config import settings

logger = logging.getLogger(__name__)

class BrokerageService:
    def __init__(self):
        self.api_key = settings.effective_t212_key.strip()
        # V1 is confirmed by the user's permission list
        self.base_url = "https://demo.trading212.com/api/v1" if settings.is_t212_demo else "https://live.trading212.com/api/v1"
        
        # In T212 Public API v1, the header is often just the key
        self.headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }

    def test_connection(self) -> bool:
        """Tests v1 endpoints with direct authorization."""
        endpoints = ["/equity/account/info", "/equity/portfolio", "/portfolio"]
        
        for ep in endpoints:
            url = f"{self.base_url}{ep}"
            try:
                logger.info(f"T212: Probing v1 {url}...")
                response = requests.get(url, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    logger.info(f"T212: SUCCESS! Connected via {url}")
                    return True
                logger.warning(f"T212: {url} rejected with {response.status_code} | Body: {response.text}")
            except Exception as e:
                logger.error(f"T212: Error connecting to {url}: {e}")
        return False

    def place_market_order(self, ticker: str, quantity: float, side: str) -> Dict[str, Any]:
        t212_ticker = f"{ticker}_US_EQ" if "_" not in ticker else ticker
        payload = {
            "symbol": t212_ticker,
            "quantity": float(quantity),
            "side": side
        }
        
        # v1 market order endpoint
        url = f"{self.base_url}/equity/orders/market"
        logger.info(f"T212: Executing {side} for {t212_ticker}")
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            if response.status_code == 200:
                logger.info(f"T212: Order SUCCESS")
                return response.json()
            
            logger.warning(f"T212: Order failed ({response.status_code}): {response.text}")
            return {"status": "error", "message": response.text}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_portfolio(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/equity/portfolio"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200: return response.json()
        except: pass
        return []
