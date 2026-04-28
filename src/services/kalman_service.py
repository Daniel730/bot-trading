import numpy as np
import logging

logger = logging.getLogger(__name__)

class KalmanFilter:
    """
    Recursive Kalman Filter for dynamic hedge ratio estimation.
    State vector x = [alpha, beta]^T
    Observation y = Price_A
    H = [1, Price_B]
    """
    def __init__(self, delta=1e-4, r=1e-3, initial_state=None, initial_covariance=None):
        """
        Initialize the filter.
        :param delta: Process noise parameter (Q = delta / (1-delta) * I)
        :param r: Measurement noise (R)
        :param initial_state: Initial [alpha, beta]
        :param initial_covariance: Initial P matrix
        """
        self.initial_state = np.array(initial_state if initial_state is not None else [0.0, 1.0])
        self.initial_covariance = np.array(initial_covariance if initial_covariance is not None else np.eye(2) * 10.0)
        
        # State vector [alpha, beta]
        self.state = self.initial_state.copy()
        
        # State covariance matrix P
        self.P = self.initial_covariance.copy()
        
        # Process noise covariance Q.
        # Delta controls how fast the state evolves. Smaller delta = more stable beta.
        self.Q_base = np.eye(2) * delta / (1 - delta)
        self.Q = self.Q_base.copy()
        self._q_inflation_remaining = 0
        self._q_inflation_total = 0
        self._q_inflation_factor = 1.0
        
        # Measurement noise variance R
        self.R = r
        
        # For Z-score calculation
        self.innovation_variance = 0.0

    def update(self, price_a, price_b):
        """
        Update the filter with new price observations.
        :param price_a: Price of Asset A (observation)
        :param price_b: Price of Asset B (regressor)
        :return: (state, innovation_variance, z_score, spread)
        """
        try:
            q_for_update = self._current_q()

            # 1. Predict (A = I, so x_minus = x, P_minus = P + Q)
            P_minus = self.P + q_for_update
            
            # 2. Observation Matrix H = [1, price_b]
            H = np.array([[1.0, price_b]])
            
            # 3. Residual / Innovation (Prior)
            y = price_a
            spread = float(y - np.dot(H, self.state).item())
            
            # 4. Residual Covariance S = H * P_minus * H^T + R
            S = np.dot(H, np.dot(P_minus, H.T)) + self.R
            self.innovation_variance = float(S.item())
            
            # Z-score (Prior)
            z_score = float(spread / np.sqrt(self.innovation_variance))

            # 5. Kalman Gain K = P_minus * H^T * S^-1
            K = np.dot(P_minus, H.T) / S
            
            # 6. Update State x = x_minus + K * spread
            new_state = self.state + K.flatten() * spread
            
            # 7. Update Covariance P = (I - K*H) * P_minus
            new_P = (np.eye(2) - np.dot(K, H)) @ P_minus
            
            # Bug 1.1: NaN/Inf Propagation Guard
            if np.isnan(new_state).any() or np.isinf(new_state).any() or np.isnan(new_P).any() or np.isinf(new_P).any():
                raise ValueError("NaN or Inf detected in Kalman update. Resetting filter.")

            # Reasonableness Guard: Prevent exploding beta
            new_state[1] = np.clip(new_state[1], 0.001, 1000.0)

            self.state = new_state
            self.P = new_P

            if self._q_inflation_remaining > 0:
                self._q_inflation_remaining -= 1
            self.Q = q_for_update

        except (ValueError, np.linalg.LinAlgError) as e:
            logger.error(f"Kalman update failed: {e}. Resetting filter to initial state.")
            self.state = self.initial_state.copy()
            self.P = self.initial_covariance.copy()
            self.Q = self.Q_base.copy()
            self._q_inflation_remaining = 0
            self.innovation_variance = 1.0
            z_score = 0.0
            spread = 0.0
        
        return self.state, self.innovation_variance, z_score, spread

    def calculate_spread_and_zscore(self, price_a, price_b):
        """
        Calculate the current spread and Z-score using filter state.
        :param price_a: Current price A
        :param price_b: Current price B
        :return: (spread, z_score)
        """
        alpha, beta = self.state
        spread = price_a - (beta * price_b + alpha)
        
        # Z-score = spread / sqrt(innovation_variance)
        if self.innovation_variance > 0:
            z_score = spread / np.sqrt(self.innovation_variance)
        else:
            z_score = 0.0
            
        return spread, z_score

    def bump_uncertainty(self, multiplier: float = 10.0):
        """Legacy one-shot P boost for session-open handling.
        Multiplies the state covariance P by *multiplier* so the filter
        can adapt faster after an overnight gap.
        """
        self.P = self.P * multiplier

    def inflate_q(self, factor: float = 5.0, n_bars: int = 10):
        """Spec 037: Linear Q-inflation for session-boundary handling.
        Inflates Q by *factor* at session open then decays it linearly
        back to the base value over the next *n_bars* update() calls.
        This lets the filter breathe through overnight gaps without
        discarding its calibrated covariance (unlike bump_uncertainty).
        """
        if factor < 1.0 or n_bars < 1:
            return
        self._q_inflation_remaining = int(n_bars)
        self._q_inflation_total = int(n_bars)
        self._q_inflation_factor = float(factor)
        self.Q = self.Q_base.copy()

    def _current_q(self):
        if self._q_inflation_remaining <= 0 or self._q_inflation_total <= 1:
            return self.Q_base.copy()
        progress = self._q_inflation_total - self._q_inflation_remaining
        decay = progress / (self._q_inflation_total - 1)
        scale = self._q_inflation_factor - ((self._q_inflation_factor - 1.0) * decay)
        return self.Q_base * scale

    def get_state_dict(self):
        """Return state for persistence."""
        return {
            "alpha_beta": self.state.tolist(), # [alpha, beta]
            "p_matrix": self.P.tolist(),
            "q_matrix": self.Q_base.tolist(),
            "r_value": float(self.R)
        }
