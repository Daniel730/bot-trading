"""Bull/bear theme agents: heuristic labeling vs gated optional LLM."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.bear_agent import bear_agent
from src.agents.bull_agent import bull_agent
from src.agents.orchestrator import (
    Orchestrator,
    _theme_agent_telemetry_verdict,
    _theme_quality_note,
)
from src.agents.theme_agent_utils import (
    HEURISTIC_SOURCE,
    LLM_SOURCE,
    QUALITY_LLM,
    QUALITY_NON_LLM,
    heuristic_confidence,
    is_heuristic_theme_verdict,
    is_usable_llm_api_key,
    reset_theme_llm_budget_for_tests,
    theme_llm_budget_status,
)


@pytest.fixture(autouse=True)
def _reset_budget():
    reset_theme_llm_budget_for_tests()
    yield
    reset_theme_llm_budget_for_tests()


def test_legacy_theater_constants_removed_from_heuristic():
    """Fixed 0.7/0.4 theater must not be the default path."""
    ctx = {"ticker_a": "AAPL", "ticker_b": "MSFT", "z_score": 2.5, "signal_id": "t1"}
    bull = heuristic_confidence("bull", ctx)
    bear = heuristic_confidence("bear", ctx)
    assert bull != 0.7
    assert bear != 0.4
    assert 0.0 < bull <= 1.0
    assert 0.0 < bear <= 1.0
    # Larger |z| raises bull support vs near-zero z.
    assert heuristic_confidence("bull", {**ctx, "z_score": 3.5}) > heuristic_confidence(
        "bull", {**ctx, "z_score": 0.5}
    )


def test_placeholder_api_keys_rejected():
    assert is_usable_llm_api_key("") is False
    assert is_usable_llm_api_key("your_openai_key") is False
    assert is_usable_llm_api_key("your_gemini_key") is False
    assert is_usable_llm_api_key("sk-proj-REALKEYVALUE123456") is True


def test_is_heuristic_theme_verdict_defaults_legacy_unlabeled():
    assert is_heuristic_theme_verdict({"confidence": 0.7}) is True
    assert is_heuristic_theme_verdict(None) is True
    assert (
        is_heuristic_theme_verdict(
            {
                "confidence": 0.8,
                "source": LLM_SOURCE,
                "quality": QUALITY_LLM,
                "llm_used": True,
            }
        )
        is False
    )
    assert (
        is_heuristic_theme_verdict(
            {
                "confidence": 0.55,
                "source": HEURISTIC_SOURCE,
                "quality": QUALITY_NON_LLM,
                "llm_used": False,
            }
        )
        is True
    )


def test_theme_telemetry_verdict_is_heuristic_not_ai_directional():
    heuristic = {
        "confidence": 0.9,
        "source": HEURISTIC_SOURCE,
        "quality": QUALITY_NON_LLM,
        "llm_used": False,
    }
    assert _theme_agent_telemetry_verdict(heuristic, directional_label="BULLISH") == "HEURISTIC"
    llm = {
        "confidence": 0.9,
        "source": LLM_SOURCE,
        "quality": QUALITY_LLM,
        "llm_used": True,
    }
    assert _theme_agent_telemetry_verdict(llm, directional_label="BULLISH") == "BULLISH"
    assert _theme_quality_note(heuristic, heuristic) == "THEME: heuristic stub (not LLM)"


@pytest.mark.asyncio
async def test_bull_bear_default_evaluate_is_heuristic_without_llm(monkeypatch):
    monkeypatch.setattr("src.agents.theme_agent_utils.settings.BULL_BEAR_LLM_ENABLED", False)
    monkeypatch.setattr("src.agents.theme_agent_utils.settings.GEMINI_API_KEY", "sk-proj-REALKEYVALUE123456")
    monkeypatch.setattr("src.agents.theme_agent_utils.settings.OPENAI_API_KEY", "sk-proj-REALKEYVALUE123456")

    ctx = {
        "ticker_a": "BTC-USD",
        "ticker_b": "ETH-USD",
        "z_score": 2.2,
        "signal_id": "theme_h1",
        "sector": "Crypto",
    }
    with patch("src.services.telemetry_service.telemetry_service.broadcast") as broadcast:
        bull = await bull_agent.evaluate(ctx)
        bear = await bear_agent.evaluate(ctx)

    assert bull["source"] == HEURISTIC_SOURCE
    assert bear["source"] == HEURISTIC_SOURCE
    assert bull["llm_used"] is False
    assert bear["llm_used"] is False
    assert "Heuristic (non-LLM)" in bull["reasoning"]
    assert "Heuristic (non-LLM)" in bear["reasoning"]
    verdicts = [call.args[1]["verdict"] for call in broadcast.call_args_list if call.args]
    assert verdicts.count("HEURISTIC") >= 2
    # Keys present but LLM disabled => no budget consumption.
    status = theme_llm_budget_status()
    assert status["hour_count"] == 0
    assert status["day_count"] == 0


@pytest.mark.asyncio
async def test_llm_budget_caps_prevent_overnight_spend(monkeypatch):
    monkeypatch.setattr("src.agents.theme_agent_utils.settings.BULL_BEAR_LLM_ENABLED", True)
    monkeypatch.setattr("src.agents.theme_agent_utils.settings.BULL_BEAR_LLM_MAX_CALLS_PER_HOUR", 1)
    monkeypatch.setattr("src.agents.theme_agent_utils.settings.BULL_BEAR_LLM_MAX_CALLS_PER_DAY", 20)
    monkeypatch.setattr("src.agents.theme_agent_utils.settings.GEMINI_API_KEY", "AIzaSyRealGeminiKey99")
    monkeypatch.setattr("src.agents.theme_agent_utils.settings.OPENAI_API_KEY", "")

    ctx = {
        "ticker_a": "AAPL",
        "ticker_b": "MSFT",
        "z_score": 2.0,
        "signal_id": "theme_budget_1",
    }

    async def fake_llm(side, signal_context):
        return {
            "confidence": 0.66,
            "argument": f"llm-{side}",
            "reasoning": f"llm-{side}",
            "source": LLM_SOURCE,
            "quality": QUALITY_LLM,
            "llm_used": True,
            "side": side,
            "active": True,
            "status": "llm",
            "llm_provider": "gemini",
        }

    with patch("src.agents.theme_agent_utils._call_theme_llm", new=fake_llm), patch(
        "src.services.telemetry_service.telemetry_service.broadcast"
    ):
        first = await bull_agent.evaluate(ctx)
        second = await bear_agent.evaluate(ctx)

    assert first["llm_used"] is True
    assert second["llm_used"] is False
    assert second["source"] == HEURISTIC_SOURCE
    assert second.get("fallback_reason") == "hourly_budget_exhausted"


@pytest.mark.asyncio
async def test_orchestrator_annotates_theme_heuristic_in_final_verdict():
    async def mock_get_system_state(key, default=None):
        values = {
            "operational_status": "NORMAL",
            "consecutive_api_timeouts": "0",
            "global_strategy_accuracy": "0.75",
        }
        return values.get(key, default)

    orch = Orchestrator()
    with (
        patch(
            "src.agents.orchestrator.macro_economic_agent.get_ticker_regime",
            new_callable=AsyncMock,
            return_value="BULLISH",
        ),
        patch(
            "src.agents.orchestrator.bull_agent.evaluate",
            new_callable=AsyncMock,
            return_value={
                "confidence": 0.62,
                "reasoning": "heuristic bull",
                "source": HEURISTIC_SOURCE,
                "quality": QUALITY_NON_LLM,
                "llm_used": False,
            },
        ),
        patch(
            "src.agents.orchestrator.bear_agent.evaluate",
            new_callable=AsyncMock,
            return_value={
                "confidence": 0.31,
                "reasoning": "heuristic bear",
                "source": HEURISTIC_SOURCE,
                "quality": QUALITY_NON_LLM,
                "llm_used": False,
            },
        ),
        patch(
            "src.agents.orchestrator.redis_service.get_fundamental_score",
            new_callable=AsyncMock,
            return_value={
                "score": 80,
                "source": "edgar",
                "available": True,
                "last_updated": 1_700_000_000,
            },
        ),
        patch(
            "src.agents.orchestrator.whale_watcher_agent.evaluate",
            new_callable=AsyncMock,
            return_value={
                "confidence_delta": 0.0,
                "confidence_multiplier": 1.0,
                "veto": False,
                "whale_score": 0.0,
                "active": False,
                "status": "inactive",
                "reasoning": "inactive",
            },
        ),
        patch(
            "src.agents.orchestrator.portfolio_manager_agent.get_optimization_advice",
            new_callable=AsyncMock,
            return_value={"is_recommended": True, "improvement": 0.1},
        ),
        patch.object(orch, "_get_system_state", side_effect=mock_get_system_state),
        patch.object(orch, "_set_system_state", new_callable=AsyncMock),
        patch.object(orch, "_get_agent_metrics", new_callable=AsyncMock, return_value=(1, 1)),
        patch("src.agents.orchestrator.telemetry_service.broadcast"),
        patch("src.agents.orchestrator.settings.PAPER_TRADING", True),
    ):
        state = await orch.ainvoke(
            {
                "signal_context": {
                    "ticker_a": "AAPL",
                    "ticker_b": "MSFT",
                    "z_score": 2.1,
                    "signal_id": "theme_orch_1",
                    "sector": "Technology",
                }
            }
        )

    assert "THEME: heuristic stub (not LLM)" in state["final_verdict"]
    assert state["bull_verdict"]["source"] == HEURISTIC_SOURCE
