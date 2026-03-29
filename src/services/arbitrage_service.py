import pandas as pd
import numpy as np
import statsmodels.api as sm
from typing import Tuple, Dict, Optional
from src.models.arbitrage_models import ArbitrageError

class ArbitrageService:
    def __init__(self):
        pass

    def calculate_beta(self, data_a: pd.Series, data_b: pd.Series) -> float:
        """Calculate the hedge ratio (beta) using Ordinary Least Squares (OLS)."""
        if data_a.empty or data_b.empty:
            raise ArbitrageError("Empty data provided for beta calculation.")
        
        # Align series by index (dates)
        combined_df = pd.concat([data_a, data_b], axis=1).dropna()
        y = combined_df.iloc[:, 0]  # ticker_a
        x = combined_df.iloc[:, 1]  # ticker_b
        
        # OLS regression: y = beta * x + alpha
        x_with_const = sm.add_constant(x)
        model = sm.OLS(y, x_with_const).fit()
        
        # Return the coefficient for ticker_b (hedge ratio)
        return float(model.params.iloc[1])

    def calculate_z_score(self, price_a: float, price_b: float, beta: float, 
                          historical_spreads: pd.Series, window: int) -> float:
        """Calculate the Z-Score of the current spread relative to its historical window."""
        current_spread = price_a - beta * price_b
        
        if len(historical_spreads) < window:
            raise ArbitrageError(f"Insufficient historical data for {window}-day window.")
        
        # Calculate moving average and standard deviation of spreads
        rolling_mean = historical_spreads.tail(window).mean()
        rolling_std = historical_spreads.tail(window).std()
        
        if rolling_std == 0:
            return 0.0
            
        return float((current_spread - rolling_mean) / rolling_std)

    def calculate_spreads(self, data_a: pd.Series, data_b: pd.Series, beta: float) -> pd.Series:
        """Calculate historical spreads: spread = ticker_a - beta * ticker_b."""
        combined_df = pd.concat([data_a, data_b], axis=1).dropna()
        return combined_df.iloc[:, 0] - beta * combined_df.iloc[:, 1]

    def get_multi_window_z_scores(self, price_a: float, price_b: float, beta: float, 
                                 historical_spreads: pd.Series, windows: list[int] = [30, 60, 90]) -> Dict[int, float]:
        """Calculate Z-Scores for multiple windows to filter technical noise."""
        results = {}
        for window in windows:
            try:
                results[window] = self.calculate_z_score(price_a, price_b, beta, historical_spreads, window)
            except ArbitrageError:
                results[window] = 0.0
        return results

    def calculate_rebalance_quantities(self, price_a: float, price_b: float, beta: float, 
                                      total_allocation: float, current_qty_a: float, current_qty_b: float) -> Dict[str, float]:
        """
        Calculate required quantities to reach the target hedge ratio.
        Target: Value_A = Total_Allocation / 2, Value_B = Value_A (adjusted by beta)
        Simplified for MVP: We aim for dollar-neutral if beta=1, or beta-adjusted neutral.
        """
        # Target values in base currency
        target_value_a = total_allocation / 2.0
        target_value_b = target_value_a # In a simple pair trade, we often balance values
        
        # In statistical arbitrage (y = beta * x), the hedge ratio is beta.
        # If we buy 1 share of A, we sell 'beta' shares of B.
        # So Value_A / Price_A = (Value_B / Price_B) / beta  => Value_B = Value_A * (Price_B * beta / Price_A)
        # However, a simpler target is to allocate half to A and let B be determined by the hedge ratio.
        
        target_qty_a = target_value_a / price_a
        target_qty_b = (target_qty_a * beta) # Based on the OLS relationship y = beta * x
        
        return {
            "ticker_a": target_qty_a - current_qty_a,
            "ticker_b": target_qty_b - current_qty_b
        }
