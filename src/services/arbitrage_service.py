import pandas as pd
from statsmodels.tsa.stattools import adfuller
import asyncio
import statsmodels.api as sm
from typing import Tuple, Dict
from src.services.kalman_service import KalmanFilter
from src.services.agent_log_service import agent_trace
from src.services.redis_service import redis_service

class ArbitrageService:
    def __init__(self):
        self.filters: Dict[str, KalmanFilter] = {}

    @agent_trace("ArbitrageService.get_or_create_filter")
    async def get_or_create_filter(self, pair_id: str, delta: float = 1e-5, r: float = 0.01, 
                             initial_state: list = None, initial_covariance: list = None) -> KalmanFilter:
        """Retrieves or initializes a Kalman filter for a specific pair, reloading from Redis if possible."""
        if pair_id in self.filters:
            return self.filters[pair_id]

        # Attempt to reload from Redis (Warm Start)
        if initial_state is None and initial_covariance is None:
            saved_state = await redis_service.get_kalman_state(pair_id)
            if saved_state:
                initial_state = saved_state['x']
                initial_covariance = saved_state['P']
                print(f"DEBUG: [ArbitrageService] Warm start successful for {pair_id}. State recovered from Redis.")
            else:
                kf = KalmanFilter(delta=delta, r=r)
                # D.1 Kalman Pre-Warming
                try:
                    from src.services.data_service import DataService
                    t_a, t_b = pair_id.split('_')
                    ds = DataService()
                    print(f"DEBUG: [ArbitrageService] No Redis state for {pair_id}. Initiating 30d historical pre-warming...")
                    df = await asyncio.to_thread(ds.get_historical_data, [t_a, t_b], "30d", "1h")
                    for i in range(len(df)):
                        price_a = float(df[t_a].iloc[i])
                        price_b = float(df[t_b].iloc[i])
                        if pd.isna(price_a) or pd.isna(price_b): continue
                        kf.update(price_a, price_b)
                    
                    self.filters[pair_id] = kf
                    print(f"DEBUG: [ArbitrageService] Pre-warming complete for {pair_id}. Filter matrices converged.")
                    return kf
                except Exception as e:
                    print(f"DEBUG: [ArbitrageService] Pre-warming failed for {pair_id}, falling back to cold start: {e}")

        self.filters[pair_id] = KalmanFilter(
            delta=delta, 
            r=r, 
            initial_state=initial_state, 
            initial_covariance=initial_covariance
        )
        return self.filters[pair_id]

    @agent_trace("ArbitrageService.save_filter_state")
    async def save_filter_state(self, pair_id: str, kf: KalmanFilter, z_score: float):
        """Persists the current state of a Kalman filter to Redis."""
        state_dict = kf.get_state_dict()
        await redis_service.save_kalman_state(
            ticker_pair=pair_id,
            x=state_dict['alpha_beta'], # [alpha, beta]
            P=state_dict['p_matrix'],
            z_score=z_score
        )

    @staticmethod
    @agent_trace("ArbitrageService.check_cointegration")
    def check_cointegration(ticker_a_series: pd.Series, ticker_b_series: pd.Series) -> Tuple[bool, float, float]:
        """
        Performs ADF test on the spread of two series.
        Returns: (is_cointegrated, p_value, hedge_ratio)
        """
        df = pd.concat([ticker_a_series, ticker_b_series], axis=1).dropna()
        if df.empty or len(df) < 20:
            return False, 1.0, 0.0
            
        s1 = df.iloc[:, 0]
        s2 = df.iloc[:, 1]

        s2_with_const = sm.add_constant(s2)
        model = sm.OLS(s1, s2_with_const)
        results = model.fit()
        
        hedge_ratio = float(results.params.iloc[1])
        intercept = float(results.params.iloc[0])
        
        spread = s1 - (hedge_ratio * s2) - intercept
        adf_result = adfuller(spread)
        p_value = float(adf_result[1])
        
        return p_value < 0.05, p_value, hedge_ratio

    @staticmethod
    def calculate_zscore(ticker_a_price: float, ticker_b_price: float, hedge_ratio: float, 
                         mean_spread: float, std_spread: float, intercept: float = 0.0) -> float:
        """
        Calculates the current Z-score of the spread using static metrics.
        """
        current_spread = ticker_a_price - (hedge_ratio * ticker_b_price) - intercept
        if std_spread == 0: return 0.0
        z_score = (current_spread - mean_spread) / std_spread
        return float(z_score)

    @staticmethod
    def get_spread_metrics(ticker_a_series: pd.Series, ticker_b_series: pd.Series, hedge_ratio: float, window: int = None) -> Dict:
        """
        Calculates spread metrics.
        """
        df = pd.concat([ticker_a_series, ticker_b_series], axis=1).dropna()
        s1 = df.iloc[:, 0]
        s2 = df.iloc[:, 1]
        
        full_spread_raw = s1 - hedge_ratio * s2
        
        if window:
            rolling_mean = full_spread_raw.rolling(window=window).mean().shift(1)
            rolling_std = full_spread_raw.rolling(window=window).std().shift(1)
            intercept = float(rolling_mean.iloc[-1])
            std = float(rolling_std.iloc[-1])
        else:
            intercept = float(full_spread_raw.mean())
            std = float(full_spread_raw.std())
        
        return {
            "mean": 0.0,
            "std": std,
            "intercept": intercept
        }

arbitrage_service = ArbitrageService()
