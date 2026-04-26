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
        self.initial_covariance = np.array(
            initial_covariance if initial_covariance is not None else np.eye(2) * 10.0
        )

        # State vector [alpha, beta]
        self.state = self.initial_state.copy()

        # State covariance matrix P
        self.P = self.initial_covariance.copy()

        # Process noise covariance Q. Delta controls how fast the state evolves.
        # Smaller delta = more stable beta. Q_base is the calibrated baseline;
        # Q is the value applied on the next update (may be transiently inflated).
        self.Q_base = np.eye(2) * delta / (1 - delta)
        self.Q = self.Q_base.copy()

        # Measurement noise variance R
        self.R = r

        # For Z-score calculation
        self.innovation_variance = 0.0

        # Adaptive Q inflation state. When > 0, the filter applies an inflated
        # Q to the next `_q_inflation_remaining` updates and decays linearly
        # back to Q_base. Used at session boundaries to let the filter
        # "breathe" through overnight gaps without losing learned state.
        self._q_inflation_remaining = 0
        self._q_inflation_initial = 0
        self._q_inflation_factor = 1.0

    def update(self, price_a, price_b):
        """
        Update the filter with new price observations.
        :param price_a: Price of Asset A (observation)
        :param price_b: Price of Asset B (regressor)
        """
        try:
            # 1. Predict (A = I, so x_minus = x, P_minus = P + Q_effective)
            Q_effective = self._effective_q()
            P_minus = self.P + Q_effective

            # 2. Observation Matrix H = [1, price_b]
            H = np.array([[1.0, price_b]])

            # 3. Residual / Innovation
            y = price_a
            innovation = y - np.dot(H, self.state)

            # 4. Residual Covariance S = H * P_minus * H^T + R
            S = np.dot(H, np.dot(P_minus, H.T)) + self.R
            self.innovation_variance = float(S.item())

            # 5. Kalman Gain K = P_minus * H^T * S^-1
            K = np.dot(P_minus, H.T) / S

            # 6. Update State x = x_minus + K * innovation
            new_state = self.state + K.flatten() * innovation

            # 7. Update Covariance P = (I - K*H) * P_minus
            new_P = (np.eye(2) - np.dot(K, H)) @ P_minus

            # Bug 1.1: NaN/Inf Propagation Guard
            if (
                np.isnan(new_state).any()
                or np.isinf(new_state).any()
                or np.isnan(new_P).any()
                or np.isinf(new_P).any()
            ):
                raise ValueError("NaN or Inf detected in Kalman update. Resetting filter.")

            # Reasonableness Guard: Prevent exploding beta.
            # beta is state[1]. We allow up to 1000 for high-price-diff pairs (BTC/ETH).
            new_state[1] = np.clip(new_state[1], 0.001, 1000.0)

            self.state = new_state
            self.P = new_P

        except (ValueError, np.linalg.LinAlgError) as e:
            logger.error(f"Kalman update failed: {e}. Resetting filter to initial state.")
            self.state = self.initial_state.copy()
            self.P = self.initial_covariance.copy()
            self.innovation_variance = 1.0  # High variance to prevent immediate trades

        return self.state, self.innovation_variance

    def calculate_spread_and_zscore(self, price_a, price_b):
        """Calculate the current spread and Z-score using filter state."""
        alpha, beta = self.state
        spread = price_a - (beta * price_b + alpha)
        if self.innovation_variance > 0:
            z_score = spread / np.sqrt(self.innovation_variance)
        else:
            z_score = 0.0
        return spread, z_score

    def get_state_dict(self):
        """Return state for persistence.

        We persist ``Q_base`` (calibrated process noise) rather than ``self.Q``
        because ``self.Q`` may be transiently inflated during a session
        boundary; serialising the inflated value would carry the inflation
        across restarts indefinitely.
        """
        return {
            "alpha_beta": self.state.tolist(),
            "p_matrix": self.P.tolist(),
            "q_matrix": self.Q_base.tolist(),
            "r_value": float(self.R),
            "q_inflation_remaining": int(self._q_inflation_remaining),
            "q_inflation_factor": float(self._q_inflation_factor),
        }

    def bump_uncertainty(self, multiplier: float = 10.0):
        """One-shot inflation of P to absorb a sudden gap.

        Note: prefer ``inflate_q`` for session-boundary handling. ``bump_uncertainty``
        is kept as a fallback when ``KALMAN_USE_Q_INFLATION`` is disabled.
        """
        self.P = self.P * multiplier
        logger.info("Kalman uncertainty bumped by factor %s", multiplier)

    def inflate_q(self, factor: float = 5.0, n_bars: int = 10) -> None:
        """Multiply Q by ``factor`` for the next ``n_bars`` updates,
        decaying linearly back to ``Q_base``.

        Why prefer this over ``bump_uncertainty``:
        - The state vector x = [alpha, beta] is preserved.
        - The inflation acts on Q (process noise), not P (estimation
          uncertainty), so the effect spans the first few bars instead of
          being absorbed by a single tick.
        - Linear decay gives a smooth transition.

        Idempotent: calling again before the previous run finishes resets
        the countdown to ``n_bars`` with the new ``factor``.
        """
        if factor < 1.0 or n_bars < 1:
            return
        self._q_inflation_factor = float(factor)
        self._q_inflation_remaining = int(n_bars)
        self._q_inflation_initial = int(n_bars)
        logger.info(
            "Kalman Q inflation engaged: factor=%.2f for %d bars (linear decay)",
            factor,
            n_bars,
        )

    def _effective_q(self) -> np.ndarray:
        """Q matrix to use on the next update step.

        While inflation is active:
            Q = Q_base * (1 + (factor - 1) * progress)
        where ``progress`` decays from 1.0 to 0.0 across the countdown bars.
        After the countdown ends, Q reverts to Q_base.
        """
        if self._q_inflation_remaining <= 0 or self._q_inflation_initial <= 0:
            self.Q = self.Q_base
            return self.Q

        progress = self._q_inflation_remaining / self._q_inflation_initial
        scale = 1.0 + (self._q_inflation_factor - 1.0) * progress
        Q_eff = self.Q_base * scale

        self._q_inflation_remaining -= 1
        if self._q_inflation_remaining == 0:
            self._q_inflation_initial = 0
            self._q_inflation_factor = 1.0

        self.Q = Q_eff
        return Q_eff
