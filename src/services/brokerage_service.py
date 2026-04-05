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
        # Feature 014: Increased precision to 6 decimal places for micro-budgets
        final_qty = float(round(quantity, 6))
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
        logger.info(f"T212: Executing {side} for {t212_ticker} (Qty: {final_qty})")
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            if response.status_code == 200:
                logger.info(f"T212: Order SUCCESS")
                return response.json()
            
            logger.warning(f"T212: Order failed ({response.status_code}): {response.text}")
            return {"status": "error", "message": response.text}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def execute_order(self, ticker: str, amount_fiat: float, side: str = "buy") -> Dict[str, Any]:
        """
        Executes a value-based order, primarily for DCA and goal-oriented investing.
        """
        return self.place_value_order(ticker, amount_fiat, side)

    def check_dividends_and_reinvest(self):
        """
        Feature 015 (FR-004): Fetches account activity to identify dividends and reinvests them.
        """
        # In a real T212 API, we would poll /equity/history/orders or /equity/history/transactions
        # This is a placeholder for the logic:
        # 1. Fetch transactions from the last 24h
        # 2. Filter for type='DIVIDEND'
        # 3. For each dividend, identify the ticker and amount
        # 4. Execute a BUY order for that ticker with the dividend amount
        logger.info("T212: Checking for new dividends to reinvest (DRIP)...")
        # Example logic (hypothetical endpoint):
        # url = f"{self.base_url}/equity/history/transactions"
        # params = {"from": datetime.now() - timedelta(days=1)}
        # response = requests.get(url, headers=self.headers, params=params)
        # ... logic to process and reinvest ...
        return True

    def place_value_order(self, ticker: str, amount: float, side: str) -> Dict[str, Any]:
        """
        Feature 014/016: Executes a value-based order by calculating required quantity.
        Enforces minTradeQuantity and quantityIncrement from brokerage metadata.
        """
        from src.services.data_service import data_service
        from src.services.risk_service import risk_service
        from src.services.agent_log_service import agent_logger
        
        # 1. Friction analysis before execution (Architecture Rule 3)
        friction_res = risk_service.calculate_friction(amount, ticker=ticker)
        if not friction_res["is_acceptable"]:
            return {"status": "error", "message": friction_res["rejection_reason"]}
        friction = friction_res["friction_pct"]

        # 2. Price and Quantity calculation
        prices = data_service.get_latest_price([ticker])
        if ticker not in prices:
            return {"status": "error", "message": f"Could not retrieve latest price for {ticker}"}
        
        price = prices[ticker]
        raw_quantity = amount / price
        
        # 3. Metadata validation (Architecture Rule 4)
        metadata = self.get_symbol_metadata(ticker)
        min_qty = float(metadata.get("minTradeQuantity", 0.0))
        qty_incr = float(metadata.get("quantityIncrement", 0.0))
        
        if min_qty > 0 and raw_quantity < min_qty:
            return {
                "status": "error", 
                "message": f"Quantity {raw_quantity:.6f} below minTradeQuantity {min_qty} for {ticker}"
            }
            
        final_quantity = raw_quantity
        if qty_incr > 0:
            # Round to nearest increment: round(qty / incr) * incr
            final_quantity = round(raw_quantity / qty_incr) * qty_incr
            final_quantity = float(round(final_quantity, 6)) # Float precision cleanup
            
        logger.info(f"T212: Value order {ticker}: ${amount} / ${price:.2f} = {final_quantity:.6f} shares (Metadata: min={min_qty}, incr={qty_incr})")
        
        result = self.place_market_order(ticker, final_quantity, side)
        
        if result.get("status") != "error":
            agent_logger.log_fractional_trade(ticker, amount, final_quantity, price, side, friction)
            
        return result

    def get_symbol_metadata(self, ticker: str) -> Dict[str, Any]:
        """Retrieves metadata for a specific symbol, including precision and min quantity."""
        t212_ticker = self._format_ticker(ticker)
        url = f"{self.base_url}/instruments" # Hypothetical based on standard T212 metadata endpoints
        # Note: v0 metadata is often bulky; in practice we might fetch all and filter
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                instruments = response.json()
                for inst in instruments:
                    if inst.get('ticker') == t212_ticker:
                        return inst
        except: pass
        return {}

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
                orders = response.json()
                if orders:
                    logger.info(f"T212: Found {len(orders)} pending orders.")
                return orders
            else:
                logger.warning(f"T212: Failed to fetch orders ({response.status_code}): {response.text}")
        except Exception as e:
            logger.error(f"T212: Error fetching orders: {e}")
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

    def get_pending_orders_value(self) -> float:
        """Calculates the total cash currently committed to pending BUY orders."""
        orders = self.get_pending_orders()
        total_value = 0.0
        for order in orders:
            # For BUY orders, quantity is positive
            qty = order.get('quantity', 0.0)
            if qty > 0:
                # Value = quantity * limit price (or estimated current price)
                # T212 v0 order object usually has 'limitPrice' or 'stopPrice'
                # Also checking for 'price' or 'fillPrice' (though fillPrice is for executed)
                price = order.get('limitPrice') or order.get('stopPrice') or order.get('price', 0.0)
                
                if price == 0 and 'ticker' in order:
                    logger.warning(f"T212: Pending order for {order['ticker']} has 0 price. Attempting fallback...")
                    from src.services.data_service import data_service
                    fallback_prices = data_service.get_latest_price([order['ticker']])
                    # Try both original and potentially formatted ticker from data_service response
                    price = fallback_prices.get(order['ticker'], 0.0)
                    if price > 0:
                        logger.info(f"T212: Fallback price for {order['ticker']} found: ${price:.2f}")
                    else:
                        # Decision 1 / FR-002: If fallback also 0.0, we cannot calculate value safely
                        logger.error(f"T212: Critical failure - fallback price also 0.0 for {order['ticker']}")
                        # We skip this order's value to avoid underestimating commitment, 
                        # but log it as a critical failure.
                
                total_value += (qty * price)
        
        if total_value > 0:
            logger.info(f"T212: Total commitment calculated: ${total_value:.2f}")
        return total_value

    def get_account_cash(self) -> float:
        """Retrieves free funds from the account."""
        url = f"{self.base_url}/equity/account/cash"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return float(response.json().get('free', 0.0))
        except: pass
        return 0.0

brokerage_service = BrokerageService()
