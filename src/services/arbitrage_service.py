import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import coint, adfuller
import statsmodels.api as sm
from typing import Tuple, Dict

class ArbitrageService:
    @staticmethod
    def check_cointegration(ticker_a_series: pd.Series, ticker_b_series: pd.Series) -> Tuple[bool, float, float]:
        """
        Performs ADF test on the spread of two series.
        Returns: (is_cointegrated, p_value, hedge_ratio)
        """
        # Align data and drop NaNs
        df = pd.concat([ticker_a_series, ticker_b_series], axis=1).dropna()
        if df.empty or len(df) < 20:
            return False, 1.0, 0.0
            
        s1 = df.iloc[:, 0]
        s2 = df.iloc[:, 1]

        # Linear regression to find hedge ratio
        model = sm.OLS(s1, s2)
        results = model.fit()
        hedge_ratio = results.params.iloc[0]
        
        spread = s1 - hedge_ratio * s2
        adf_result = adfuller(spread)
        p_value = adf_result[1]
        
        return p_value < 0.05, p_value, hedge_ratio

    @staticmethod
    def calculate_zscore(ticker_a_price: float, ticker_b_price: float, hedge_ratio: float, 
                         mean_spread: float, std_spread: float) -> float:
        """
        Calculates the current Z-score of the spread.
        """
        current_spread = ticker_a_price - hedge_ratio * ticker_b_price
        if std_spread == 0: return 0.0
        z_score = (current_spread - mean_spread) / std_spread
        return z_score

    @staticmethod
    def get_spread_metrics(ticker_a_series: pd.Series, ticker_b_series: pd.Series, hedge_ratio: float) -> Dict:
        """
        Calculates rolling mean and std of the spread.
        """
        df = pd.concat([ticker_a_series, ticker_b_series], axis=1).dropna()
        s1 = df.iloc[:, 0]
        s2 = df.iloc[:, 1]
        spread = s1 - hedge_ratio * s2
        return {
            "mean": spread.mean(),
            "std": spread.std()
        }

arbitrage_service = ArbitrageService()
