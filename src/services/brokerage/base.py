from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from decimal import Decimal

class AbstractBrokerageProvider(ABC):
    @abstractmethod
    def test_connection(self) -> bool:
        """
        Check whether the provider can connect to and authenticate with the brokerage API.
        
        Returns:
            true if connectivity and authentication succeed, false otherwise.
        """
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
        """
        Place a market-style order for the specified ticker.
        
        Parameters:
            ticker (str): Symbol to trade.
            quantity (float): Number of units to buy or sell.
            side (str): Order side, e.g., "buy" or "sell".
            limit_price (Optional[float]): When provided, treat the request as a limit-slippage order using this price; otherwise execute with provider-defined market behavior.
            client_order_id (Optional[str]): Optional client-supplied identifier to attach to the order.
        
        Returns:
            Dict[str, Any]: Provider-specific order result payload describing the submitted order and its execution details.
        """
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
        """
        Place an order sized by currency value for a given ticker and side.
        
        Parameters:
        	ticker (str): Symbol or instrument identifier to trade.
        	amount (float): Order size expressed in currency units (e.g., USD).
        	side (str): Order side, typically 'buy' or 'sell'.
        	price (Optional[float]): Optional reference or limit price to guide execution.
        	client_order_id (Optional[str]): Optional client-supplied identifier for the order.
        
        Returns:
        	order_result (Dict[str, Any]): Provider-specific order response payload containing execution and order metadata.
        """
        pass

    @abstractmethod
    def get_portfolio(self) -> List[Dict[str, Any]]:
        """
        Retrieve current portfolio holdings.
        
        Returns:
            List[Dict[str, Any]]: A list of holding dictionaries, each representing a position with provider-specific fields (commonly including keys such as `ticker`, `quantity`, and `market_value`).
        """
        pass

    @abstractmethod
    def get_positions(self, ticker: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve open positions, optionally filtered by ticker.
        
        Parameters:
        	ticker (Optional[str]): If provided, only positions for this ticker are returned.
        
        Returns:
        	positions (List[Dict[str, Any]]): A list of position dictionaries representing open positions; each dictionary contains provider-specific fields (e.g., ticker, quantity, average price, unrealized P&L).
        """
        pass

    @abstractmethod
    def get_account_cash(self) -> float:
        """
        Get the currently available free cash balance for trading.
        
        Returns:
            float: Available free cash amount.
        """
        pass

    @abstractmethod
    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """
        Fetches currently pending orders.
        
        Returns:
            List[Dict[str, Any]]: A list of pending order objects, each represented as a dictionary containing the provider's order fields.
        """
        pass

    @abstractmethod
    def get_symbol_metadata(self, ticker: str) -> Dict[str, Any]:
        """
        Retrieve metadata and trading constraints for the given symbol.
        
        Parameters:
            ticker (str): Symbol identifier to look up.
        
        Returns:
            Dict[str, Any]: Mapping of metadata fields for the symbol, such as tick size, minimum quantity, lot/board lot size, price and quantity increments, and other provider-specific trading constraints.
        """
        pass
