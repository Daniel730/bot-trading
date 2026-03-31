import numpy as np
from typing import Tuple, Dict, Optional

class KalmanFilter:
    """
    Recursive Kalman Filter for estimating a dynamic hedge ratio and intercept.
    
    State vector x = [alpha, beta]^T
    Observation equation: y = Hx + v, where H = [1, Price_B]
    """
    def __init__(self, delta: float = 1e-5, R: float = 0.01):
        """
        Initializes the filter.
        :param delta: Control for process noise (Q matrix). Small delta = stable beta.
        :param R: Measurement noise variance. Large R = trust new data less.
        """
        self.delta = delta
        self.R = R
        
        # State vector [intercept, hedge_ratio]^T
        self.x = np.zeros((2, 1))
        
        # State covariance matrix (Initial high uncertainty)
        self.P = np.eye(2)
        
        # Process noise covariance matrix
        self.Q = self.delta / (1 - self.delta) * np.eye(2)
        
        # Residual variance (for Z-score calculation)
        self.ve = 1.0

    def initialize(self, alpha: float, beta: float, p_matrix: Optional[np.ndarray] = None):
        """Seeds the filter with initial OLS values or persisted state."""
        self.x = np.array([[alpha], [beta]])
        if p_matrix is not None:
            self.P = p_matrix
        else:
            self.P = np.eye(2)

    def update(self, price_a: float, price_b: float) -> Tuple[float, float, float]:
        """
        Performs the Predict-Correct cycle for one new observation.
        :return: (beta, alpha, z_score)
        """
        # 1. Prediction (Transition matrix is Identity)
        # x_hat = x
        # P_hat = P + Q
        P_hat = self.P + self.Q
        
        # 2. Measurement update
        # H matrix: [1, price_b]
        H = np.array([[1.0, price_b]])
        
        # Expected value: y_hat = H * x_hat
        y_hat = float(np.dot(H, self.x))
        
        # Error (Innovation): et = y - y_hat
        et = price_a - y_hat
        
        # Error variance: Qt = H * P_hat * H^T + R
        Qt = float(np.dot(H, np.dot(P_hat, H.T))) + self.R
        self.ve = Qt # Keep for Z-score
        
        # 3. Kalman Gain: K = P_hat * H^T / Qt
        K = np.dot(P_hat, H.T) / Qt
        
        # 4. Correct State and Covariance
        self.x = self.x + K * et
        self.P = P_hat - np.dot(K, np.dot(H, P_hat))
        
        # Feature 007: Exploding Beta Guard (Stability)
        # Prevent beta from becoming unrealistic during zero-liquidity or flash crashes
        self.x[1, 0] = np.clip(self.x[1, 0], 0.01, 100.0)
        
        # Extract results
        alpha = float(self.x[0, 0])
        beta = float(self.x[1, 0])
        
        # Z-score: Innovation divided by its standard deviation
        z_score = et / np.sqrt(Qt)
        
        return beta, alpha, z_score

    def get_state(self) -> Dict:
        """Returns the current state for persistence."""
        return {
            "alpha": float(self.x[0, 0]),
            "beta": float(self.x[1, 0]),
            "p_matrix": self.P.tolist(),
            "ve": self.ve
        }
