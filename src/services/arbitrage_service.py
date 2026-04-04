import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import coint, adfuller
import statsmodels.api as sm
from typing import Tuple, Dict, Optional
from src.services.kalman_service import KalmanFilter
from src.services.agent_log_service import agent_trace

class ArbitrageService:
    def __init__(self):
        self.filters: Dict[str, KalmanFilter] = {}

    @agent_trace("ArbitrageService.get_or_create_filter")
    def get_or_create_filter(self, pair_id: str, delta: float = 1e-5, r: float = 0.01, 
                             initial_state: list = None, initial_covariance: list = None) -> KalmanFilter:
        """Retrieves or initializes a Kalman filter for a specific pair."""
        if pair_id not in self.filters:
            self.filters[pair_id] = KalmanFilter(
                delta=delta, 
                r=r, 
                initial_state=initial_state, 
                initial_covariance=initial_covariance
            )
        return self.filters[pair_id]

    @staticmethod
    @agent_trace("ArbitrageService.check_cointegration")
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
        hedge_ratio = float(results.params.iloc[0])
        
        spread = s1 - hedge_ratio * s2
        adf_result = adfuller(spread)
        p_value = float(adf_result[1])
        
        return p_value < 0.05, p_value, hedge_ratio

    @staticmethod
    def calculate_zscore(ticker_a_price: float, ticker_b_price: float, hedge_ratio: float, 
                         mean_spread: float, std_spread: float) -> float:
        """
        Calculates the current Z-score of the spread using static metrics.
        """
        current_spread = ticker_a_price - hedge_ratio * ticker_b_price
        if std_spread == 0: return 0.0
        z_score = (current_spread - mean_spread) / std_spread
        return float(z_score)

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
            "mean": float(spread.mean()),
            "std": float(spread.std())
        }

arbitrage_service = ArbitrageService()
