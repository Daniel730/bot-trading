import logging

logger = logging.getLogger(__name__)

class WhaleWatcherAgent:
    """
    Dummy WhaleWatcherAgent. 
    Legacy implementation moved to legacy/agents/whale_watcher_agent.py
    """
    active = False
    status_name = "inactive"
    mode = "legacy_neutral"
    inactive_reason = (
        "Whale watcher is inactive: active cache-backed flow analysis is in legacy mode."
    )

    def status(self) -> dict:
        return {
            "active": self.active,
            "status": self.status_name,
            "mode": self.mode,
            "reason": self.inactive_reason,
        }

    def neutral(self, reasoning: str) -> dict:
        return {
            "confidence_delta": 0.0,
            "confidence_multiplier": 1.0,
            "veto": False,
            "whale_score": 0.0,
            "active": self.active,
            "status": self.status_name,
            "mode": self.mode,
            "inactive_reason": self.inactive_reason,
            "reasoning": reasoning,
        }

    async def evaluate(self, signal_context: dict) -> dict:
        return self.neutral(self.inactive_reason)

whale_watcher_agent = WhaleWatcherAgent()
