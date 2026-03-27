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

    def update_pair_parameters(self, historical_data: pd.DataFrame) -> Dict[str, float]:
        """
        Calculates hedge ratio, mean spread, and std spread from historical data.
        Uses OLS regression (Price A = Hedge Ratio * Price B + Intercept).
        """
        y = historical_data['asset_a']
        x = historical_data['asset_b']
        x = sm.add_constant(x)
        
        model = sm.OLS(y, x).fit()
        hedge_ratio = model.params['asset_b']
        
        # Calculate spread: Price A - (Hedge Ratio * Price B)
        # Note: We ignore the intercept for the spread calculation itself as we calculate the mean spread
        spreads = historical_data['asset_a'] - (hedge_ratio * historical_data['asset_b'])
        
        return {
            'hedge_ratio': hedge_ratio,
            'mean_spread': spreads.mean(),
            'std_spread': spreads.std()
        }
