from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from decimal import Decimal

class AbstractBrokerageProvider(ABC):
    @abstractmethod
    def test_connection(self) -> bool:
        """Verify API connectivity and authentication."""
        pass

    @abstractmethod
    async def place_market_order(
        self, 
        ticker: str, 
        quantity: float, 
        side: str, 
        limit_price: Optional[float] = None, 
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a market or limit-slippage order."""
        pass

    @abstractmethod
    async def place_value_order(
        self,
        ticker: str,
        amount: float,
        side: str,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a value-based order (amount in currency)."""
        pass

    @abstractmethod
    def get_portfolio(self) -> List[Dict[str, Any]]:
        """Fetch current portfolio holdings."""
        pass

    @abstractmethod
    def get_positions(self, ticker: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch open positions."""
        pass

    @abstractmethod
    def get_account_cash(self) -> float:
        """Fetch available free cash."""
        pass

    @abstractmethod
    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """Fetch currently pending orders."""
        pass

    @abstractmethod
    def get_symbol_metadata(self, ticker: str) -> Dict[str, Any]:
        """Fetch instrument-specific constraints (tick size, min qty)."""
        pass
