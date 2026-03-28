import pandas as pd
import numpy as np
import statsmodels.api as sm
import logging
from typing import Tuple, Dict, Any, List
from src.models.arbitrage_models import ArbitragePair, OrderType

logger = logging.getLogger(__name__)

class ArbitrageService:
    def __init__(self):
        pass

    def calculate_hedge_ratio(self, data_a: pd.Series, data_b: pd.Series) -> float:
        """
        Calculates the hedge ratio using OLS (Ordinary Least Squares).
        y = beta * x + alpha
        Returns beta.
        """
        X = sm.add_constant(data_b)
        model = sm.OLS(data_a, X).fit()
        beta = model.params.iloc[1]
        return float(beta)

    def calculate_spread(self, data_a: pd.Series, data_b: pd.Series, beta: float) -> pd.Series:
        """
        Calculates the spread: spread = price_a - beta * price_b
        """
        return data_a - beta * data_b

    def calculate_z_score(self, spread: pd.Series, window: int) -> pd.Series:
        """
        Calculates the normalized Z-Score for a given window.
        Z = (spread - rolling_mean) / rolling_std
        """
        rolling_mean = spread.rolling(window=window).mean()
        rolling_std = spread.rolling(window=window).std()
        z_score = (spread - rolling_mean) / rolling_std
        return z_score

    def get_latest_z_score(self, data_a: pd.Series, data_b: pd.Series, beta: float, window: int) -> float:
        """
        Calculates the latest Z-Score for a pair.
        """
        spread = self.calculate_spread(data_a, data_b, beta)
        z_scores = self.calculate_z_score(spread, window)
        return float(z_scores.iloc[-1])

    def get_multi_window_z_scores(self, data_a: pd.Series, data_b: pd.Series, beta: float, windows: List[int]) -> Dict[int, float]:
        """
        Calculates the latest Z-Score for a pair across multiple windows.
        """
        spread = self.calculate_spread(data_a, data_b, beta)
        results = {}
        for window in windows:
            z_scores = self.calculate_z_score(spread, window)
            results[window] = float(z_scores.iloc[-1])
        return results

    def calculate_rebalance_orders(self, ticker_a: str, ticker_b: str, beta: float, 
                                   current_price_a: float, current_price_b: float, 
                                   target_value: float, z_score: float) -> List[Dict[str, Any]]:
        """
        Calculates the necessary buy/sell orders for an atomic swap.
        Ensures SELL orders are listed before BUY orders to free up cash/margin.
        Returns a list of order dictionaries.
        """
        orders = []
        
        if z_score > 2.5:
            # Sell A, Buy B
            orders.append({"ticker": ticker_a, "quantity": -1.0, "type": OrderType.SELL})
            orders.append({"ticker": ticker_b, "quantity": beta, "type": OrderType.BUY})
            
        elif z_score < -2.5:
            # Buy A, Sell B
            # Order: Sell B first, then Buy A
            orders.append({"ticker": ticker_b, "quantity": -beta, "type": OrderType.SELL})
            orders.append({"ticker": ticker_a, "quantity": 1.0, "type": OrderType.BUY})
            
        return orders
