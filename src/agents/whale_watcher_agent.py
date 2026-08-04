import logging

from src.config import settings

logger = logging.getLogger(__name__)


class WhaleWatcherAgent:
    """Hard-dormant whale-flow stub on the orchestrator hot path.

    Cache-backed analysis was removed with the ``legacy/`` tree and is
    not imported by runtime. ``WHALE_WATCHER_ENABLED`` and related knobs are
    reserved for a future restored evaluator (GitHub #91); flipping the flag
    alone must not enable veto or confidence side effects.
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
            "enabled_flag": bool(getattr(settings, "WHALE_WATCHER_ENABLED", False)),
            "enabled_flag_honored": False,
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
            "enabled_flag": bool(getattr(settings, "WHALE_WATCHER_ENABLED", False)),
            "enabled_flag_honored": False,
            "reasoning": reasoning,
        }

    async def evaluate(self, signal_context: dict) -> dict:
        if bool(getattr(settings, "WHALE_WATCHER_ENABLED", False)):
            logger.debug(
                "WHALE_WATCHER_ENABLED=true ignored: hot-path evaluator remains inactive "
                "(signal_id=%s)",
                (signal_context or {}).get("signal_id", "N/A"),
            )
        return self.neutral(self.inactive_reason)


whale_watcher_agent = WhaleWatcherAgent()
