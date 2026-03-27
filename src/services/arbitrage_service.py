import pandas as pd
import numpy as np
import statsmodels.api as sm
from typing import Dict, Any

class ArbitrageService:
    def __init__(self):
        pass

    def calculate_spread(self, price_a: float, price_b: float, hedge_ratio: float) -> float:
        """
        Spread = Price A - (Hedge Ratio * Price B)
        """
        return price_a - (hedge_ratio * price_b)

    def calculate_z_score(self, current_spread: float, mean_spread: float, std_spread: float) -> float:
        """
        Z = (Current Spread - Mean Spread) / Std Dev Spread
        """
        if std_spread == 0:
            return 0.0
        return (current_spread - mean_spread) / std_spread

    def calculate_rebalance_orders(
        self,
        current_positions: Dict[str, float],
        current_prices: Dict[str, float],
        target_weights: Dict[str, float],
        free_cash: float,
        max_allocation_pct: float
    ) -> Dict[str, float]:
        """
        Calculates the quantity to buy/sell for each asset to reach target weights,
        applying a risk cap (max_allocation_pct of free_cash) to any BUY order.
        Returns a dict of {ticker: quantity_change}.
        """
        # Calculate Total Portfolio Value
        invested_value = sum(
            current_positions.get(ticker, 0.0) * current_prices.get(ticker, 0.0)
            for ticker in target_weights
        )
        total_value = invested_value + free_cash
        
        orders = {}
        max_trade_value = free_cash * (max_allocation_pct / 100.0)
        
        for ticker, target_weight in target_weights.items():
            price = current_prices.get(ticker)
            if not price or price <= 0:
                continue
                
            current_qty = current_positions.get(ticker, 0.0)
            target_value = total_value * target_weight
            current_value = current_qty * price
            
            value_diff = target_value - current_value
            
            # Apply risk cap only to BUY orders (value_diff > 0)
            if value_diff > max_trade_value:
                value_diff = max_trade_value
            
            # Quantity to order (can be negative for SELL)
            order_qty = value_diff / price
            orders[ticker] = round(order_qty, 6)
            
        return orders
