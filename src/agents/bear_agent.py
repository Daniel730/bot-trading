"""Bear theme agent — structural-break / risk argument for the orchestrator.

Default path is an explicit z-score heuristic (``source=heuristic_stub``), not
LLM theater. Optional Gemini/OpenAI scoring requires ``BULL_BEAR_LLM_ENABLED``
plus usable keys and remaining hourly/daily budget caps.
"""

from src.agents.theme_agent_utils import evaluate_theme
from src.services.telemetry_service import telemetry_service


class BearAgent:
    async def evaluate(self, signal_context: dict) -> dict:
        """Evaluate the signal from a bearish / break-risk perspective."""
        result = await evaluate_theme("bear", signal_context)

        telemetry_service.broadcast(
            "thought",
            {
                "agent_name": "BEAR_AGENT",
                "signal_id": signal_context.get("signal_id", "N/A"),
                "ticker_pair": f"{signal_context['ticker_a']}_{signal_context['ticker_b']}",
                "thought": result.get("reasoning") or result.get("argument", ""),
                "verdict": "HEURISTIC" if result.get("source") == "heuristic_stub" else "BEARISH",
                "source": result.get("source"),
                "quality": result.get("quality"),
                "llm_used": result.get("llm_used", False),
            },
        )
        return result


bear_agent = BearAgent()
