from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.whale_watcher_agent import whale_watcher_agent
from src.services.whale_watcher_service import whale_watcher_service


def test_normalize_event_infers_exchange_flow_and_stablecoin():
    event = whale_watcher_service.normalize_event({
        "symbol": "USDC",
        "timestamp": "2026-04-29T12:00:00Z",
        "value_usd": 12_000_000,
        "from_owner_type": "treasury",
        "to_owner_type": "exchange",
        "tx_hash": "0xabc",
        "source": "whale_alert",
    })

    assert event.symbol == "USDC"
    assert event.exchange_inflow is True
    assert event.exchange_outflow is False
    assert event.stablecoin is True
    assert event.confidence == 1.0


def test_summarize_events_scores_exchange_flows(monkeypatch):
    monkeypatch.setattr("src.config.settings.WHALE_WATCHER_MIN_VALUE_USD", 1_000_000.0)
    monkeypatch.setattr("src.config.settings.WHALE_WATCHER_EXTREME_VALUE_USD", 10_000_000.0)
    monkeypatch.setattr("src.config.settings.WHALE_WATCHER_ROLLING_WINDOW_SECONDS", 1800)

    now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
    events = [
        whale_watcher_service.normalize_event({
            "symbol": "BTC",
            "timestamp": "2026-04-29T11:58:00+00:00",
            "value_usd": 12_000_000,
            "from_owner_type": "exchange",
            "to_owner_type": "custody",
            "source": "fixture",
        }).to_dict(),
        whale_watcher_service.normalize_event({
            "symbol": "BTC",
            "timestamp": "2026-04-29T11:57:00+00:00",
            "value_usd": 8_000_000,
            "from_owner_type": "unknown",
            "to_owner_type": "unknown",
            "source": "fixture",
        }).to_dict(),
    ]

    summary = whale_watcher_service.summarize_events("BTC", events, now=now)

    assert summary["event_count"] == 2
    assert summary["exchange_outflow_count"] == 1
    assert summary["whale_exchange_outflow_score"] > 0.7
    assert summary["noise_penalty"] > 0
    assert summary["single_leg_pressure_score"] > 0


def test_agent_vetoes_aggregated_conflicting_exchange_flows(monkeypatch):
    monkeypatch.setattr("src.config.settings.WHALE_WATCHER_VETO_MIN_EVENTS", 2)
    monkeypatch.setattr("src.config.settings.WHALE_WATCHER_EXTREME_VALUE_USD", 50_000_000.0)
    monkeypatch.setattr("src.config.settings.WHALE_WATCHER_VETO_SCORE", 0.85)

    # z < 0 means Long BTC / Short ETH. Heavy BTC exchange inflows conflict
    # with the proposed long leg and should veto only after aggregation.
    context = {
        "summary_a": {
            **whale_watcher_service.empty_summary("BTC"),
            "event_count": 2,
            "exchange_inflow_count": 2,
            "exchange_inflow_value_usd": 65_000_000.0,
            "whale_exchange_inflow_score": 0.9,
            "single_leg_pressure_score": -0.9,
        },
        "summary_b": whale_watcher_service.empty_summary("ETH"),
        "stablecoin_summary": whale_watcher_service.empty_summary("STABLECOIN"),
    }

    verdict = whale_watcher_agent._score_pair_context("BTC-USD", "ETH-USD", -2.4, context)

    assert verdict["veto"] is True
    assert verdict["confidence_multiplier"] == 0.0
    assert "Rolling exchange inflows" in verdict["reasoning"]


def test_agent_penalizes_single_conflicting_flow_without_veto(monkeypatch):
    monkeypatch.setattr("src.config.settings.WHALE_WATCHER_RISK_MULTIPLIER", 0.85)
    monkeypatch.setattr("src.config.settings.WHALE_WATCHER_SUPPORT_MULTIPLIER", 1.05)
    monkeypatch.setattr("src.config.settings.WHALE_WATCHER_VETO_MIN_EVENTS", 2)

    context = {
        "summary_a": {
            **whale_watcher_service.empty_summary("BTC"),
            "event_count": 1,
            "exchange_inflow_count": 1,
            "exchange_inflow_value_usd": 80_000_000.0,
            "whale_exchange_inflow_score": 0.95,
            "single_leg_pressure_score": -0.95,
        },
        "summary_b": whale_watcher_service.empty_summary("ETH"),
        "stablecoin_summary": whale_watcher_service.empty_summary("STABLECOIN"),
    }

    verdict = whale_watcher_agent._score_pair_context("BTC-USD", "ETH-USD", -2.4, context)

    assert verdict["veto"] is False
    assert verdict["confidence_delta"] < 0
    assert verdict["confidence_multiplier"] < 1.0


@pytest.mark.asyncio
async def test_orchestrator_applies_whale_veto():
    from src.agents.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    input_data = {
        "signal_context": {
            "signal_id": "whale_veto_1",
            "ticker_a": "BTC-USD",
            "ticker_b": "ETH-USD",
            "z_score": -2.3,
            "sector": "Crypto L1",
        }
    }

    async def mock_get_system_state(key, default=None):
        if key == "operational_status":
            return "NORMAL"
        if key == "consecutive_api_timeouts":
            return "0"
        return default

    with patch("src.agents.orchestrator.macro_economic_agent.get_ticker_regime", new_callable=AsyncMock, return_value="BULLISH"), \
         patch("src.agents.orchestrator.bull_agent.evaluate", new_callable=AsyncMock, return_value={"confidence": 0.7, "reasoning": "ok"}), \
         patch("src.agents.orchestrator.bear_agent.evaluate", new_callable=AsyncMock, return_value={"confidence": 0.2, "reasoning": "ok"}), \
         patch("src.agents.orchestrator.redis_service.get_fundamental_score", new_callable=AsyncMock, return_value={"score": 100}), \
         patch("src.agents.orchestrator.whale_watcher_agent.evaluate", new_callable=AsyncMock, return_value={
             "confidence_delta": -1.0,
             "confidence_multiplier": 0.0,
             "veto": True,
             "whale_score": -1.0,
             "reasoning": "VETO: Whale watcher test veto.",
         }), \
         patch("src.agents.orchestrator.persistence_service.get_system_state", new=mock_get_system_state), \
         patch("src.agents.orchestrator.persistence_service.set_system_state", new_callable=AsyncMock), \
         patch("src.services.telemetry_service.telemetry_service.broadcast", return_value=None):
        state = await orchestrator.ainvoke(input_data)

    assert state["final_confidence"] == 0.0
    assert state["final_verdict"] == "VETO: Whale watcher test veto."
    assert state["whale_verdict"]["veto"] is True
