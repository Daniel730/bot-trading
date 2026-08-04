from unittest.mock import AsyncMock, patch
import time

import pytest

from src.agents.orchestrator import Orchestrator, _whale_effects_apply
from src.agents.whale_watcher_agent import whale_watcher_agent


def test_legacy_whale_watcher_reports_inactive_status():
    status = whale_watcher_agent.status()

    assert status["active"] is False
    assert status["status"] == "inactive"
    assert status["mode"] == "legacy_neutral"
    assert status["enabled_flag_honored"] is False
    assert "legacy" in status["reason"].lower()


def test_whale_effects_apply_requires_explicit_active():
    assert _whale_effects_apply(None) is False
    assert _whale_effects_apply({}) is False
    assert _whale_effects_apply({"active": False, "status": "inactive", "veto": True}) is False
    assert _whale_effects_apply({"veto": True, "confidence_multiplier": 0.5}) is False
    assert _whale_effects_apply({"active": True, "status": "active", "veto": True}) is True


@pytest.mark.asyncio
async def test_legacy_whale_watcher_evaluate_marks_inactive_not_neutral_protection():
    verdict = await whale_watcher_agent.evaluate({
        "ticker_a": "BTC-USD",
        "ticker_b": "ETH-USD",
        "signal_id": "whale_inactive_1",
    })

    assert verdict["active"] is False
    assert verdict["status"] == "inactive"
    assert verdict["mode"] == "legacy_neutral"
    assert verdict["veto"] is False
    assert verdict["confidence_multiplier"] == 1.0
    assert verdict["confidence_delta"] == 0.0
    assert verdict["whale_score"] == 0.0
    assert verdict["enabled_flag_honored"] is False
    assert "inactive" in verdict["reasoning"].lower()
    assert _whale_effects_apply(verdict) is False


@pytest.mark.asyncio
async def test_whale_enabled_flag_does_not_activate_stub():
    with patch("src.agents.whale_watcher_agent.settings") as mock_settings:
        mock_settings.WHALE_WATCHER_ENABLED = True
        verdict = await whale_watcher_agent.evaluate({
            "ticker_a": "BTC-USD",
            "ticker_b": "ETH-USD",
            "signal_id": "whale_flag_ignored_1",
        })

    assert verdict["active"] is False
    assert verdict["status"] == "inactive"
    assert verdict["veto"] is False
    assert verdict["enabled_flag"] is True
    assert verdict["enabled_flag_honored"] is False
    assert _whale_effects_apply(verdict) is False


def _orchestrator_base_patches(*, whale_return: dict, metrics_mock: AsyncMock | None = None):
    async def mock_get_system_state(key, default=None):
        values = {
            "operational_status": "NORMAL",
            "consecutive_api_timeouts": "0",
            "global_strategy_accuracy": "0.75",
        }
        return values.get(key, default)

    metrics = metrics_mock or AsyncMock(return_value=(1, 1))
    return [
        patch(
            "src.agents.orchestrator.macro_economic_agent.get_ticker_regime",
            new_callable=AsyncMock,
            return_value="BULLISH",
        ),
        patch(
            "src.agents.orchestrator.bull_agent.evaluate",
            new_callable=AsyncMock,
            return_value={"confidence": 0.7, "reasoning": "ok"},
        ),
        patch(
            "src.agents.orchestrator.bear_agent.evaluate",
            new_callable=AsyncMock,
            return_value={"confidence": 0.2, "reasoning": "ok"},
        ),
        patch(
            "src.agents.orchestrator.redis_service.get_fundamental_score",
            new_callable=AsyncMock,
            return_value={
                "score": 100,
                "source": "edgar",
                "available": True,
                "last_updated": time.time(),
            },
        ),
        patch(
            "src.agents.orchestrator.whale_watcher_agent.evaluate",
            new_callable=AsyncMock,
            return_value=whale_return,
        ),
        patch(
            "src.agents.orchestrator.portfolio_manager_agent.get_optimization_advice",
            new_callable=AsyncMock,
            return_value={"is_recommended": True, "improvement": 0.0},
        ),
        patch(
            "src.agents.orchestrator.persistence_service.get_system_state",
            new=mock_get_system_state,
        ),
        patch(
            "src.agents.orchestrator.persistence_service.set_system_state",
            new_callable=AsyncMock,
        ),
        patch(
            "src.agents.orchestrator.persistence_service.get_agent_metrics",
            new=metrics,
        ),
        patch(
            "src.agents.orchestrator.telemetry_service.broadcast",
            return_value=None,
        ),
    ]


@pytest.mark.asyncio
async def test_orchestrator_reports_inactive_whale_watcher():
    orchestrator = Orchestrator()
    input_data = {
        "signal_context": {
            "signal_id": "whale_inactive_orchestrator_1",
            "ticker_a": "BTC-USD",
            "ticker_b": "ETH-USD",
            "z_score": -2.3,
            "sector": "Crypto L1",
        }
    }

    with patch(
        "src.agents.orchestrator.macro_economic_agent.get_ticker_regime",
        new_callable=AsyncMock,
        return_value="BULLISH",
    ), patch(
        "src.agents.orchestrator.bull_agent.evaluate",
        new_callable=AsyncMock,
        return_value={"confidence": 0.7, "reasoning": "ok"},
    ), patch(
        "src.agents.orchestrator.bear_agent.evaluate",
        new_callable=AsyncMock,
        return_value={"confidence": 0.2, "reasoning": "ok"},
    ), patch(
        "src.agents.orchestrator.redis_service.get_fundamental_score",
        new_callable=AsyncMock,
        return_value={
            "score": 100,
            "source": "edgar",
            "available": True,
            "last_updated": time.time(),
        },
    ), patch(
        "src.agents.orchestrator.portfolio_manager_agent.get_optimization_advice",
        new_callable=AsyncMock,
        return_value={"is_recommended": True, "improvement": 0.0},
    ), patch(
        "src.agents.orchestrator.persistence_service.get_system_state",
        new=AsyncMock(
            side_effect=lambda key, default=None: {
                "operational_status": "NORMAL",
                "consecutive_api_timeouts": "0",
                "global_strategy_accuracy": "0.75",
            }.get(key, default)
        ),
    ), patch(
        "src.agents.orchestrator.persistence_service.set_system_state",
        new_callable=AsyncMock,
    ), patch(
        "src.agents.orchestrator.persistence_service.get_agent_metrics",
        new_callable=AsyncMock,
        return_value=(1, 1),
    ), patch(
        "src.agents.orchestrator.telemetry_service.broadcast",
        return_value=None,
    ) as mock_broadcast:
        state = await orchestrator.ainvoke(input_data)

    assert state["whale_verdict"]["active"] is False
    assert state["whale_verdict"]["status"] == "inactive"
    assert "WHALE score=" not in state["final_verdict"]
    assert not state["final_verdict"].startswith("VETO: Whale")

    whale_thoughts = [
        call.args[1]
        for call in mock_broadcast.call_args_list
        if call.args[0] == "thought"
        and call.args[1].get("agent_name") == "WHALE_WATCHER"
    ]
    assert whale_thoughts
    assert whale_thoughts[0]["verdict"] == "INACTIVE"
    assert "inactive" in whale_thoughts[0]["thought"].lower()


@pytest.mark.asyncio
async def test_orchestrator_ignores_inactive_whale_veto_and_boost():
    """Defense-in-depth: inactive payloads must not veto or scale confidence."""
    orchestrator = Orchestrator()
    input_data = {
        "signal_context": {
            "signal_id": "whale_inactive_poison_1",
            "ticker_a": "BTC-USD",
            "ticker_b": "ETH-USD",
            "z_score": -2.3,
            "sector": "Crypto L1",
        }
    }
    poison = {
        "confidence_delta": -0.4,
        "confidence_multiplier": 0.5,
        "veto": True,
        "whale_score": 0.99,
        "active": False,
        "status": "inactive",
        "mode": "legacy_neutral",
        "reasoning": "poisoned inactive veto must be ignored",
    }
    metrics = AsyncMock(return_value=(1, 1))
    patches = _orchestrator_base_patches(whale_return=poison, metrics_mock=metrics)

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
            patches[6], patches[7], patches[8], patches[9]:
        state = await orchestrator.ainvoke(input_data)

    assert state["final_confidence"] > 0.0
    assert "poisoned" not in state["final_verdict"].lower()
    assert "WHALE score=" not in state["final_verdict"]
    metric_agents = [call.args[0] for call in metrics.call_args_list]
    assert "WHALE_WATCHER" not in metric_agents
    assert set(metric_agents) <= {"BULL_AGENT", "BEAR_AGENT", "SEC_AGENT"}


@pytest.mark.asyncio
async def test_orchestrator_skips_mab_whale_weight_allocation():
    """Whale is not a MAB arm — only bull/bear/(sec) Thompson weights."""
    orchestrator = Orchestrator()
    input_data = {
        "signal_context": {
            "signal_id": "whale_no_mab_1",
            "ticker_a": "BTC-USD",
            "ticker_b": "ETH-USD",
            "z_score": -2.1,
            "sector": "Crypto L1",
        }
    }
    metrics = AsyncMock(return_value=(5, 2))
    patches = _orchestrator_base_patches(
        whale_return={
            "confidence_delta": 0.0,
            "confidence_multiplier": 1.0,
            "veto": False,
            "whale_score": 0.0,
            "active": False,
            "status": "inactive",
            "mode": "legacy_neutral",
            "reasoning": "inactive",
        },
        metrics_mock=metrics,
    )

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
            patches[6], patches[7], patches[8], patches[9]:
        state = await orchestrator.ainvoke(input_data)

    assert state["final_confidence"] > 0.0
    metric_agents = [call.args[0] for call in metrics.call_args_list]
    assert metric_agents == ["BULL_AGENT", "BEAR_AGENT", "SEC_AGENT"] or metric_agents == [
        "BULL_AGENT",
        "BEAR_AGENT",
    ]
    assert "WHALE_WATCHER" not in metric_agents
