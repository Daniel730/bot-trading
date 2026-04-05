import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import coint, adfuller
import statsmodels.api as sm
from typing import Tuple, Dict, Optional
from src.services.kalman_service import KalmanFilter
from src.services.agent_log_service import agent_trace
from src.models.persistence import PersistenceManager
from src.config import settings

class ArbitrageService:
    def __init__(self, persistence: Optional[PersistenceManager] = None):
        self.filters: Dict[str, KalmanFilter] = {}
        self.persistence = persistence or PersistenceManager(settings.DB_PATH)

    @agent_trace("ArbitrageService.get_or_create_filter")
    def get_or_create_filter(self, pair_id: str, delta: float = 1e-5, r: float = 0.01, 
                             initial_state: list = None, initial_covariance: list = None) -> KalmanFilter:
        """Retrieves or initializes a Kalman filter for a specific pair, reloading from DB if possible."""
        if pair_id in self.filters:
            return self.filters[pair_id]

        # Attempt to reload from persistence if no initial state provided
        if initial_state is None and initial_covariance is None:
            saved_state = self.persistence.load_kalman_state(pair_id)
            if saved_state:
                initial_state = [saved_state['alpha'], saved_state['beta']]
                initial_covariance = saved_state['p_matrix']

        self.filters[pair_id] = KalmanFilter(
            delta=delta, 
            r=r, 
            initial_state=initial_state, 
            initial_covariance=initial_covariance
        )
        return self.filters[pair_id]

    @agent_trace("ArbitrageService.save_filter_state")
    def save_filter_state(self, pair_id: str, kf: KalmanFilter, innovation_var: float = None):
        """Persists the current state of a Kalman filter to the database."""
        state_dict = kf.get_state_dict()
        self.persistence.save_kalman_state(
            pair_id=pair_id,
            alpha=state_dict['alpha'],
            beta=state_dict['beta'],
            p_matrix=state_dict['p_matrix'],
            q_matrix=state_dict['q_matrix'],
            r_value=state_dict['r_value'],
            ve=innovation_var
        )

    @staticmethod
    @agent_trace("ArbitrageService.check_cointegration")
    def check_cointegration(ticker_a_series: pd.Series, ticker_b_series: pd.Series) -> Tuple[bool, float, float]:
        """
        Performs ADF test on the spread of two series.
        Returns: (is_cointegrated, p_value, hedge_ratio)
        Decision 5: Explicitly use sm.add_constant() for mathematical intercept.
        """
        # Align data and drop NaNs
        df = pd.concat([ticker_a_series, ticker_b_series], axis=1).dropna()
        if df.empty or len(df) < 20:
            return False, 1.0, 0.0
            
        s1 = df.iloc[:, 0]
        s2 = df.iloc[:, 1]

        # Decision 5: Linear regression with intercept (constant)
        s2_with_const = sm.add_constant(s2)
        model = sm.OLS(s1, s2_with_const)
        results = model.fit()
        
        # results.params[0] is the constant (intercept), results.params[1] is the hedge_ratio
        intercept = float(results.params.iloc[0])
        hedge_ratio = float(results.params.iloc[1])
        
        # Decision 5: Subtract intercept to center the spread at zero for ADF/Z-score
        spread = s1 - (hedge_ratio * s2) - intercept
        adf_result = adfuller(spread)
        p_value = float(adf_result[1])
        
        return p_value < 0.05, p_value, hedge_ratio

    @staticmethod
    def calculate_zscore(ticker_a_price: float, ticker_b_price: float, hedge_ratio: float, 
                         mean_spread: float, std_spread: float, intercept: float = 0.0) -> float:
        """
        Calculates the current Z-score of the spread using static metrics.
        Includes intercept adjustment for statistical rigor.
        """
        current_spread = ticker_a_price - (hedge_ratio * ticker_b_price) - intercept
        if std_spread == 0: return 0.0
        z_score = (current_spread - mean_spread) / std_spread
        return float(z_score)

    @staticmethod
    def get_spread_metrics(ticker_a_series: pd.Series, ticker_b_series: pd.Series, hedge_ratio: float, window: int = None) -> Dict:
        """
        Calculates spread metrics. If window is provided, uses trailing metrics to avoid look-ahead bias.
        Decision 5: Now recalculates intercept to ensure zero-mean spread metrics.
        """
        df = pd.concat([ticker_a_series, ticker_b_series], axis=1).dropna()
        s1 = df.iloc[:, 0]
        s2 = df.iloc[:, 1]
        
        # Bug 1.3: Prevent Look-Ahead Bias
        # If we are calculating a baseline for immediate use, we use the tail.
        # If we are calculating historical series, we MUST shift.
        
        # Re-estimate intercept for the provided hedge_ratio
        # spread = s1 - beta*s2 - alpha -> alpha = mean(s1 - beta*s2)
        full_spread_raw = s1 - hedge_ratio * s2
        
        if window:
            # Trailing window calculation (Shifted by 1 to exclude current point from the mean/std)
            rolling_mean = full_spread_raw.rolling(window=window).mean().shift(1)
            rolling_std = full_spread_raw.rolling(window=window).std().shift(1)
            intercept = float(rolling_mean.iloc[-1])
            std = float(rolling_std.iloc[-1])
        else:
            intercept = float(full_spread_raw.mean())
            std = float(full_spread_raw.std())
        
        return {
            "mean": 0.0, # Centered by definition of intercept
            "std": std,
            "intercept": intercept
        }

arbitrage_service = ArbitrageService()
