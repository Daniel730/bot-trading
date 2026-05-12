from unittest.mock import AsyncMock, patch

import pytest

from src.agents.whale_watcher_agent import whale_watcher_agent


def test_legacy_whale_watcher_reports_inactive_status():
    status = whale_watcher_agent.status()

    assert status["active"] is False
    assert status["status"] == "inactive"
    assert status["mode"] == "legacy_neutral"
    assert "legacy" in status["reason"].lower()


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
    assert "inactive" in verdict["reasoning"].lower()


@pytest.mark.asyncio
async def test_orchestrator_reports_inactive_whale_watcher():
    from src.agents.orchestrator import Orchestrator

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

    async def mock_get_system_state(key, default=None):
        values = {
            "operational_status": "NORMAL",
            "consecutive_api_timeouts": "0",
            "global_strategy_accuracy": "0.75",
        }
        return values.get(key, default)

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
        return_value={"score": 100},
    ), patch(
        "src.agents.orchestrator.portfolio_manager_agent.get_optimization_advice",
        new_callable=AsyncMock,
        return_value={"is_recommended": True, "improvement": 0.0},
    ), patch(
        "src.agents.orchestrator.persistence_service.get_system_state",
        new=mock_get_system_state,
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

    whale_thoughts = [
        call.args[1]
        for call in mock_broadcast.call_args_list
        if call.args[0] == "thought"
        and call.args[1].get("agent_name") == "WHALE_WATCHER"
    ]
    assert whale_thoughts
    assert whale_thoughts[0]["verdict"] == "INACTIVE"
    assert "inactive" in whale_thoughts[0]["thought"].lower()
