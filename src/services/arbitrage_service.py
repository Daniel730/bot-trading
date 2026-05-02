import pandas as pd
from statsmodels.tsa.stattools import adfuller
import statsmodels.api as sm
from typing import Optional, Tuple, Dict
from src.services.kalman_service import KalmanFilter
from src.services.agent_log_service import agent_trace
import logging
from src.services.redis_service import redis_service
from src.config import settings

logger = logging.getLogger(__name__)

class ArbitrageService:
    def __init__(self):
        self.filters: Dict[str, KalmanFilter] = {}

    @agent_trace("ArbitrageService.get_or_create_filter")
    async def get_or_create_filter(self, pair_id: str, delta: float = 1e-5, r: float = 0.01, 
                             initial_state: list = None, initial_covariance: list = None,
                             prewarm_data: Optional[pd.DataFrame] = None) -> KalmanFilter:
        """Retrieves or initializes a Kalman filter for a specific pair, reloading from Redis if possible."""
        if pair_id in self.filters:
            return self.filters[pair_id]

        # Attempt to reload from Redis (Warm Start)
        if initial_state is None and initial_covariance is None:
            saved_state = await redis_service.get_kalman_state(pair_id)
            if saved_state:
                initial_state = saved_state['x']
                initial_covariance = saved_state['P']
                logger.info(f"[ArbitrageService] Warm start successful for {pair_id}. State recovered from Redis.")
                kf = KalmanFilter(delta=delta, r=r, initial_state=initial_state, initial_covariance=initial_covariance)
                # Restore innovation_variance so z-scores are valid immediately on first scan
                kf.innovation_variance = saved_state.get('innovation_variance', 0.0)
                self.filters[pair_id] = kf
                return kf
            else:
                kf = KalmanFilter(delta=delta, r=r)
                # D.1 Kalman Pre-Warming
                try:
                    from src.services.data_service import DataService
                    t_a, t_b = pair_id.split('_')
                    
                    df = prewarm_data
                    if df is None:
                        ds = DataService()
                        logger.info(f"[ArbitrageService] No Redis state or prewarm_data for {pair_id}. Initiating 30d historical pre-warming...")
                        df = await ds.get_historical_data_async([t_a, t_b], "30d", "1h")
                    
                    if df is not None and not df.empty:
                        for i in range(len(df)):
                            # Find columns that match ticker names
                            col_a = next((c for c in df.columns if t_a in str(c)), None)
                            col_b = next((c for c in df.columns if t_b in str(c)), None)
                            if not col_a or not col_b: continue

                            price_a = float(df[col_a].iloc[i])
                            price_b = float(df[col_b].iloc[i])
                            if pd.isna(price_a) or pd.isna(price_b): continue
                            kf.update(price_a, price_b)
                    
                    self.filters[pair_id] = kf
                    logger.info(f"[ArbitrageService] Pre-warming complete for {pair_id}. Filter matrices converged.")
                    return kf
                except Exception as e:
                    logger.warning(f"[ArbitrageService] Pre-warming failed for {pair_id}, falling back to cold start: {e}")

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
            z_score=z_score,
            innovation_variance=kf.innovation_variance
        )

    @staticmethod
    @agent_trace("ArbitrageService.check_cointegration")
    def check_cointegration(ticker_a_series: pd.Series, ticker_b_series: pd.Series) -> Tuple[bool, float, float]:
        """
        Performs ADF test on the spread of two series.
        Returns: (is_cointegrated, p_value, hedge_ratio)
        """
        df = pd.concat([ticker_a_series, ticker_b_series], axis=1).dropna()
        if df.empty or len(df) < settings.COINTEGRATION_MIN_OBSERVATIONS:
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

        return p_value < settings.COINTEGRATION_PVALUE_THRESHOLD, p_value, hedge_ratio

    @staticmethod
    @agent_trace("ArbitrageService.check_rolling_cointegration")
    def check_rolling_cointegration(
        ticker_a_series: pd.Series,
        ticker_b_series: pd.Series,
        window: int = 60,
        step: int = 5,
        min_pass_rate: float = 0.7,
        pvalue_threshold: Optional[float] = None,
    ) -> Dict:
        """Rolling Engle-Granger cointegration stability check.

        A single ADF test on a static window can flatter a pair that was
        coíntegrated for half the period and decoupled for the other half.
        For Kalman pairs trading we need stability — the cointegration must
        hold across most rolling sub-windows of the calibration period.

        Parameters
        ----------
        window:
            Number of observations per rolling window (typically 60 hourly
            bars ≈ ~2 weeks of US trading).
        step:
            Stride between consecutive windows.
        min_pass_rate:
            Minimum fraction of windows that must reject the unit-root null
            for the pair to be considered stably cointegrated. 0.7 is the
            empirical sweet spot — too lenient (0.5) admits regime-shifting
            pairs, too strict (0.9) rejects almost all real-world pairs.
        pvalue_threshold:
            Override for `settings.COINTEGRATION_PVALUE_THRESHOLD`.

        Returns
        -------
        dict with keys:
            ``stable``        — bool, True iff pass rate >= min_pass_rate
            ``pass_rate``     — fraction of windows that passed
            ``windows_total`` — number of windows actually evaluated
            ``windows_pass``  — number of windows that passed
            ``median_pvalue`` — median ADF p-value across windows
            ``last_pvalue``   — ADF p-value of the most recent window
        """
        threshold = (
            pvalue_threshold
            if pvalue_threshold is not None
            else settings.COINTEGRATION_PVALUE_THRESHOLD
        )
        df = pd.concat([ticker_a_series, ticker_b_series], axis=1).dropna()
        n = len(df)
        empty_result = {
            "stable": False,
            "pass_rate": 0.0,
            "windows_total": 0,
            "windows_pass": 0,
            "median_pvalue": 1.0,
            "last_pvalue": 1.0,
        }
        if n < window or window < settings.COINTEGRATION_MIN_OBSERVATIONS:
            return empty_result

        s1 = df.iloc[:, 0]
        s2 = df.iloc[:, 1]
        pvalues: list[float] = []
        for start in range(0, n - window + 1, step):
            end = start + window
            sub_a = s1.iloc[start:end]
            sub_b = s2.iloc[start:end]
            try:
                sub_b_const = sm.add_constant(sub_b)
                ols = sm.OLS(sub_a, sub_b_const).fit()
                hedge = float(ols.params.iloc[1])
                intercept = float(ols.params.iloc[0])
                spread = sub_a - (hedge * sub_b) - intercept
                # adfuller raises on degenerate spreads (constant) — skip those.
                if float(spread.std()) <= 0.0:
                    continue
                _, pval, *_ = adfuller(spread, autolag="AIC")
                pvalues.append(float(pval))
            except Exception as e:
                logger.debug("rolling-coint window %s-%s failed: %s", start, end, e)
                continue

        if not pvalues:
            return empty_result

        passed = [p for p in pvalues if p < threshold]
        pass_rate = len(passed) / len(pvalues)
        median_p = float(pd.Series(pvalues).median())
        return {
            "stable": pass_rate >= min_pass_rate,
            "pass_rate": pass_rate,
            "windows_total": len(pvalues),
            "windows_pass": len(passed),
            "median_pvalue": median_p,
            "last_pvalue": pvalues[-1],
        }

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
            # Bug M-01: Look-ahead bias elimination.
            # Exclude the final observation to prevent causality violation.
            intercept = float(full_spread_raw.iloc[:-1].mean())
            adjusted_spread = full_spread_raw - intercept
            std = float(adjusted_spread.iloc[:-1].std())

        return {
            "mean": intercept,  # Bug C-01: Fixed — was hardcoded 0.0
            "std": std,
            "intercept": intercept
        }

def _get_spread_metrics_fixed(ticker_a_series: pd.Series, ticker_b_series: pd.Series, hedge_ratio: float, window: int = None) -> Dict:
    df = pd.concat([ticker_a_series, ticker_b_series], axis=1).dropna()
    s1 = df.iloc[:, 0]
    s2 = df.iloc[:, 1]
    full_spread_raw = s1 - hedge_ratio * s2
    if window:
        rolling_intercept = full_spread_raw.rolling(window=window).mean().shift(1)
        intercept = float(rolling_intercept.iloc[-1])
        adjusted_spread = full_spread_raw - intercept
        std = float(adjusted_spread.rolling(window=window).std().shift(1).iloc[-1])
    else:
        intercept = float(full_spread_raw.iloc[:-1].mean())
        adjusted_spread = full_spread_raw - intercept
        std = float(adjusted_spread.iloc[:-1].std())
    return {"mean": 0.0, "std": std, "intercept": intercept}


ArbitrageService.get_spread_metrics = staticmethod(_get_spread_metrics_fixed)

arbitrage_service = ArbitrageService()
