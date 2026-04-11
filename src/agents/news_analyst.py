from typing import Dict
from src.config import settings

class NewsAnalyst:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY

    async def analyze_sentiment(self, tickers: list) -> Dict:
        """
        Analyzes news sentiment and detects event spikes for given tickers.
        """
        # Placeholder for Gemini API call
        print(f"Analyzing news for {tickers} using Gemini...")
        return {
            "sentiment_score": 0.5, # Neutral-positive
            "event_spike": False,
            "reasoning": "No major earnings or SEC filings detected in the last 24h."
        }

news_analyst = NewsAnalyst()
