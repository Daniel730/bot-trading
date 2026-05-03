import logging

logger = logging.getLogger(__name__)

class WhaleWatcherAgent:
    """
    Dummy WhaleWatcherAgent. 
    Legacy implementation moved to legacy/agents/whale_watcher_agent.py
    """
    def neutral(self, reasoning: str) -> dict:
        return {
            "confidence_delta": 0.0,
            "confidence_multiplier": 1.0,
            "veto": False,
            "whale_score": 0.0,
            "reasoning": reasoning,
        }

    async def evaluate(self, signal_context: dict) -> dict:
        return self.neutral("Whale watcher agent is in legacy mode.")

whale_watcher_agent = WhaleWatcherAgent()
