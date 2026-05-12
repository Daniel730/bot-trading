from unittest.mock import AsyncMock, patch

import pytest

from src.agents.orchestrator import Orchestrator
from src.config import settings


@pytest.mark.asyncio
async def test_live_mode_vetoes_missing_fundamental_score(monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "ORCH_FUNDAMENTAL_DEFAULT_SCORE", 75)
    monkeypatch.setattr(settings, "ORCH_FUNDAMENTAL_VETO_SCORE", 40)

    orchestrator = Orchestrator()
    input_data = {
        "signal_context": {
            "signal_id": "live_missing_fundamental_1",
            "ticker_a": "AAPL",
            "ticker_b": "MSFT",
            "hedge_ratio": 1.0,
            "z_score": 2.5,
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
        return_value={"confidence": 0.95, "reasoning": "bullish"},
    ), patch(
        "src.agents.orchestrator.bear_agent.evaluate",
        new_callable=AsyncMock,
        return_value={"confidence": 0.05, "reasoning": "not bearish"},
    ), patch(
        "src.agents.orchestrator.redis_service.get_fundamental_score",
        new_callable=AsyncMock,
        side_effect=[None, {"score": 90}],
    ), patch(
        "src.agents.orchestrator.whale_watcher_agent.evaluate",
        new_callable=AsyncMock,
        return_value={
            "confidence_delta": 0.0,
            "confidence_multiplier": 1.0,
            "veto": False,
            "whale_score": 0.0,
            "reasoning": "neutral",
        },
    ), patch(
        "src.agents.orchestrator.portfolio_manager_agent.get_optimization_advice",
        new_callable=AsyncMock,
        return_value={"is_recommended": True, "improvement": 0.0},
    ) as mock_portfolio_advice, patch(
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
    ):
        state = await orchestrator.ainvoke(input_data)

    assert state["final_confidence"] == 0.0
    assert state["fundamental_verdict"]["veto"] is True
    assert state["fundamental_verdict"]["missing_tickers"] == ["AAPL"]
    assert "VETO" in state["final_verdict"]
    assert "unknown fundamental state" in state["final_verdict"].lower()
    mock_portfolio_advice.assert_not_awaited()
