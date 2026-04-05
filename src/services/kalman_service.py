import numpy as np

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
        # State vector [alpha, beta]
        self.state = np.array(initial_state if initial_state is not None else [0.0, 1.0])
        
        # State covariance matrix P
        self.P = np.array(initial_covariance if initial_covariance is not None else np.eye(2) * 10.0)
        
        # Process noise covariance Q
        # Delta controls how fast the state evolves. Smaller delta = more stable beta.
        self.Q = np.eye(2) * delta / (1 - delta)
        
        # Measurement noise variance R
        self.R = r
        
        # For Z-score calculation
        self.innovation_variance = 0.0

    def update(self, price_a, price_b):
        """
        Update the filter with new price observations.
        :param price_a: Price of Asset A (observation)
        :param price_b: Price of Asset B (regressor)
        """
        # 1. Predict (A = I, so x_minus = x, P_minus = P + Q)
        # x_minus = self.state
        P_minus = self.P + self.Q
        
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
        self.state = self.state + K.flatten() * innovation
        
        # 7. Update Covariance P = (I - K*H) * P_minus
        self.P = (np.eye(2) - np.dot(K, H)) @ P_minus
        
        # Reasonableness Guard: Prevent exploding beta
        # beta is state[1]
        self.state[1] = np.clip(self.state[1], 0.1, 10.0)
        
        return self.state, self.innovation_variance

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

    def get_state_dict(self):
        """Return state for persistence."""
        return {
            "alpha": float(self.state[0]),
            "beta": float(self.state[1]),
            "p_matrix": self.P.tolist(),
            "q_matrix": self.Q.tolist(),
            "r_value": float(self.R)
        }
