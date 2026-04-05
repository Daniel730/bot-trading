import logging

class MacroEconomicAgent:
    def __init__(self, rate_threshold: float = 0.05, inflation_threshold: float = 0.04):
        self.rate_threshold = rate_threshold
        self.inflation_threshold = inflation_threshold
        self.logger = logging.getLogger(__name__)

    def analyze_market_state(self, interest_rate: float, inflation: float) -> str:
        """
        Determines if the market is RISK_ON or RISK_OFF based on macro indicators.
        """
        if interest_rate > self.rate_threshold or inflation > self.inflation_threshold:
            self.logger.info(f"Macro state: RISK_OFF (Rates: {interest_rate}, Inflation: {inflation})")
            return "RISK_OFF"
        
        self.logger.info(f"Macro state: RISK_ON (Rates: {interest_rate}, Inflation: {inflation})")
        return "RISK_ON"

    async def fetch_current_indicators(self) -> dict:
        """
        Fetches latest macro data from external sources (e.g., ^TNX).
        Placeholder implementation.
        """
        return {
            "interest_rate": 0.042,
            "inflation": 0.031
        }
