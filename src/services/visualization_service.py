import matplotlib.pyplot as plt
import numpy as np
import os
from src.services.agent_log_service import agent_trace
import logging

logger = logging.getLogger(__name__)

class VisualizationService:
    def __init__(self):
        self.charts_dir = "logs/charts"
        os.makedirs(self.charts_dir, exist_ok=True)

    @agent_trace("VisualizationService.generate_monte_carlo")
    def generate_monte_carlo(self, ticker: str, amount: float, days: int = 180, simulations: int = 100) -> str:
        """
        Generates a Monte Carlo simulation chart for a given asset.
        """
        try:
            # Simplified Monte Carlo using random walk
            # Real implementation would use historical mean/vol from DataService
            mu = 0.0005 # Expected daily return (approx 12% annually)
            sigma = 0.015 # Daily volatility
            
            plt.figure(figsize=(10, 6))
            
            for i in range(simulations):
                daily_returns = np.random.normal(mu, sigma, days)
                price_path = amount * (1 + daily_returns).cumprod()
                plt.plot(price_path, color='blue', alpha=0.1)
                
            plt.title(f"Monte Carlo: ${amount:.2f} in {ticker} ({days} days)")
            plt.xlabel("Days")
            plt.ylabel("Value ($)")
            plt.grid(True)
            
            file_path = os.path.join(self.charts_dir, f"{ticker}_mc_{days}d.png")
            plt.savefig(file_path)
            plt.close()
            
            logger.info(f"VisualizationService: Monte Carlo saved to {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"VisualizationService: Monte Carlo failed: {e}")
            return ""

visualization_service = VisualizationService()
