import requests
import logging
import base64
from typing import List, Dict, Any
from src.config import settings

logger = logging.getLogger(__name__)

class BrokerageService:
    def __init__(self):
        self.api_key = settings.effective_t212_key.strip()
        self.api_secret = settings.T212_API_SECRET.strip()
        
        # V0 is the standard for the current public beta API
        self.base_url = "https://demo.trading212.com/api/v0" if settings.is_t212_demo else "https://live.trading212.com/api/v0"
        
        # Feature 004: T212 v0 requires Basic Auth (Key:Secret base64 encoded)
        if self.api_key and self.api_secret:
            auth_str = f"{self.api_key}:{self.api_secret}"
            encoded_auth = base64.b64encode(auth_str.encode()).decode()
            self.headers = {
                "Authorization": f"Basic {encoded_auth}",
                "Content-Type": "application/json"
            }
        else:
            # Fallback for v1 or key-only if secret is missing (likely to 401 on v0)
            self.headers = {
                "Authorization": self.api_key,
                "Content-Type": "application/json"
            }

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
        if "_" in ticker: return ticker # Already formatted
        
        if ticker.endswith(".DE"):
            return ticker.replace(".DE", "_DE_EQ")
        if ticker.endswith(".PA"):
            return ticker.replace(".PA", "_PA_EQ")
        if ticker.endswith(".L"):
            return ticker.replace(".L", "_L_EQ")
            
        return f"{ticker}_US_EQ"

    def place_market_order(self, ticker: str, quantity: float, side: str) -> Dict[str, Any]:
        t212_ticker = self._format_ticker(ticker)
        
        # T212 v0 Market Order: Positive quantity for BUY, Negative for SELL
        final_qty = float(round(quantity, 2))
        if side.upper() == "SELL":
            final_qty = -abs(final_qty)
        else:
            final_qty = abs(final_qty)

        payload = {
            "ticker": t212_ticker,
            "quantity": final_qty
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

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """Retrieves a list of all active/pending orders."""
        url = f"{self.base_url}/equity/orders"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200: 
                return response.json()
        except: pass
        return []

    def has_pending_order(self, ticker: str) -> bool:
        """Checks if there is already a pending order for the given ticker."""
        orders = self.get_pending_orders()
        t212_ticker = self._format_ticker(ticker)
        return any(o.get('ticker') == t212_ticker for o in orders)

    def is_ticker_owned(self, ticker: str) -> bool:
        """Checks if the account currently holds the given ticker."""
        portfolio = self.get_portfolio()
        t212_ticker = self._format_ticker(ticker)
        return any(pos.get('ticker') == t212_ticker for pos in portfolio)

    def get_account_cash(self) -> float:
        """Retrieves free funds from the account."""
        url = f"{self.base_url}/equity/account/cash"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return float(response.json().get('free', 0.0))
        except: pass
        return 0.0
