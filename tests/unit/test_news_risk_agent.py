"""Unit tests for the veto-only News Risk overlay."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.news_risk_agent import (
    NewsRiskAgent,
    map_headline_tickers,
    news_effects_apply,
    score_headline_materiality,
)
from src.agents.orchestrator import Orchestrator
from src.services.news_feed import NewsHeadline, StubNewsFeed


def test_map_headline_tickers_aliases_and_exact():
    tickers = map_headline_tickers("Coca-Cola and PepsiCo face antitrust probe; KO mentioned")
    assert "KO" in tickers
    assert "PEP" in tickers


def test_score_headline_materiality_high_severity():
    score, hits = score_headline_materiality("Company files for Chapter 11 bankruptcy protection")
    assert score >= 0.9
    assert "bankruptcy" in hits or "chapter 11" in hits


def test_score_headline_materiality_benign():
    score, hits = score_headline_materiality("Analysts discuss seasonal soft-drink demand trends")
    assert score == 0.0
    assert hits == []


@pytest.mark.asyncio
async def test_news_risk_disabled_is_inactive_no_veto(monkeypatch):
    monkeypatch.setattr("src.agents.news_risk_agent.settings.NEWS_RISK_ENABLED", False)
    agent = NewsRiskAgent(feed=StubNewsFeed())
    verdict = await agent.evaluate({"ticker_a": "KO", "ticker_b": "PEP", "signal_id": "n1"})
    assert verdict["active"] is False
    assert verdict["veto"] is False
    assert verdict["confidence_multiplier"] == 1.0
    assert news_effects_apply(verdict) is False


@pytest.mark.asyncio
async def test_news_risk_missing_feed_inactive_no_veto(monkeypatch):
    monkeypatch.setattr("src.agents.news_risk_agent.settings.NEWS_RISK_ENABLED", True)
    agent = NewsRiskAgent(feed=StubNewsFeed())
    with patch(
        "src.agents.news_risk_agent.redis_service.get_json",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "src.agents.news_risk_agent.redis_service.set_json",
        new_callable=AsyncMock,
    ):
        verdict = await agent.evaluate({"ticker_a": "KO", "ticker_b": "PEP", "signal_id": "n2"})
    assert verdict["active"] is False
    assert verdict["veto"] is False
    assert "no-veto" in verdict["reasoning"].lower() or "unavailable" in verdict["reasoning"].lower()


class _FixedFeed:
    name = "fixed"

    def __init__(self, headlines):
        self._headlines = headlines

    async def fetch(self, *, limit: int = 50):
        return self._headlines[:limit]


@pytest.mark.asyncio
async def test_news_risk_vetoes_material_relevant_headline(monkeypatch):
    monkeypatch.setattr("src.agents.news_risk_agent.settings.NEWS_RISK_ENABLED", True)
    monkeypatch.setattr("src.agents.news_risk_agent.settings.NEWS_RISK_TTL_SECONDS", 7200)
    monkeypatch.setattr("src.agents.news_risk_agent.settings.NEWS_RISK_VETO_SCORE", 0.75)
    feed = _FixedFeed(
        [
            NewsHeadline(
                title="Coca-Cola faces SEC charges over accounting fraud",
                summary="Regulators allege material misstatements",
                published_at=time.time() - 60,
                source="test",
            )
        ]
    )
    agent = NewsRiskAgent(feed=feed)
    with patch(
        "src.agents.news_risk_agent.redis_service.get_json",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "src.agents.news_risk_agent.redis_service.set_json",
        new_callable=AsyncMock,
    ):
        verdict = await agent.evaluate({"ticker_a": "KO", "ticker_b": "PEP", "signal_id": "n3"})
    assert verdict["active"] is True
    assert verdict["veto"] is True
    assert "KO" in verdict["matched_tickers"]
    assert verdict["materiality"] >= 0.75
    assert news_effects_apply(verdict) is True


@pytest.mark.asyncio
async def test_news_risk_no_veto_when_unrelated_ticker(monkeypatch):
    monkeypatch.setattr("src.agents.news_risk_agent.settings.NEWS_RISK_ENABLED", True)
    feed = _FixedFeed(
        [
            NewsHeadline(
                title="NVIDIA bankruptcy rumor spreads on social media",
                published_at=time.time() - 30,
            )
        ]
    )
    agent = NewsRiskAgent(feed=feed)
    with patch(
        "src.agents.news_risk_agent.redis_service.get_json",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "src.agents.news_risk_agent.redis_service.set_json",
        new_callable=AsyncMock,
    ):
        verdict = await agent.evaluate({"ticker_a": "KO", "ticker_b": "PEP", "signal_id": "n4"})
    assert verdict["active"] is True
    assert verdict["veto"] is False
    assert verdict["matched_tickers"] == []


@pytest.mark.asyncio
async def test_news_risk_ignores_stale_headline_outside_ttl(monkeypatch):
    monkeypatch.setattr("src.agents.news_risk_agent.settings.NEWS_RISK_ENABLED", True)
    monkeypatch.setattr("src.agents.news_risk_agent.settings.NEWS_RISK_TTL_SECONDS", 3600)
    feed = _FixedFeed(
        [
            NewsHeadline(
                title="PepsiCo files for Chapter 11 bankruptcy",
                published_at=time.time() - 10_000,
            )
        ]
    )
    agent = NewsRiskAgent(feed=feed)
    with patch(
        "src.agents.news_risk_agent.redis_service.get_json",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "src.agents.news_risk_agent.redis_service.set_json",
        new_callable=AsyncMock,
    ):
        verdict = await agent.evaluate({"ticker_a": "KO", "ticker_b": "PEP", "signal_id": "n5"})
    assert verdict["active"] is True
    assert verdict["veto"] is False


def _orchestrator_patches(*, news_return: dict):
    async def mock_get_system_state(key, default=None):
        values = {
            "operational_status": "NORMAL",
            "consecutive_api_timeouts": "0",
            "global_strategy_accuracy": "0.75",
        }
        return values.get(key, default)

    return [
        patch(
            "src.agents.orchestrator.macro_economic_agent.get_ticker_regime",
            new_callable=AsyncMock,
            return_value="BULLISH",
        ),
        patch(
            "src.agents.orchestrator.bull_agent.evaluate",
            new_callable=AsyncMock,
            return_value={"confidence": 0.7, "reasoning": "ok", "source": "heuristic_stub"},
        ),
        patch(
            "src.agents.orchestrator.bear_agent.evaluate",
            new_callable=AsyncMock,
            return_value={"confidence": 0.2, "reasoning": "ok", "source": "heuristic_stub"},
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
            return_value={
                "active": False,
                "status": "inactive",
                "veto": False,
                "confidence_multiplier": 1.0,
                "confidence_delta": 0.0,
                "whale_score": 0.0,
                "reasoning": "inactive",
            },
        ),
        patch(
            "src.agents.orchestrator.news_risk_agent.evaluate",
            new_callable=AsyncMock,
            return_value=news_return,
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
            new_callable=AsyncMock,
            return_value=(1, 1),
        ),
        patch(
            "src.agents.orchestrator.telemetry_service.broadcast",
            return_value=None,
        ),
    ]


@pytest.mark.asyncio
async def test_orchestrator_respects_active_news_veto():
    orchestrator = Orchestrator()
    input_data = {
        "signal_context": {
            "signal_id": "news_veto_orch_1",
            "ticker_a": "KO",
            "ticker_b": "PEP",
            "z_score": -2.2,
            "sector": "Consumer",
        }
    }
    news_return = {
        "active": True,
        "status": "active",
        "veto": True,
        "confidence_multiplier": 0.0,
        "materiality": 0.95,
        "matched_tickers": ["KO"],
        "reasoning": "VETO: NEWS RISK material headline on KO",
    }
    patches = _orchestrator_patches(news_return=news_return)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
            patches[6], patches[7], patches[8], patches[9], patches[10]:
        state = await orchestrator.ainvoke(input_data)

    assert state["final_confidence"] == 0.0
    assert state["final_verdict"].startswith("VETO:")
    assert "NEWS" in state["final_verdict"].upper()


@pytest.mark.asyncio
async def test_orchestrator_ignores_inactive_news_veto_poison():
    orchestrator = Orchestrator()
    input_data = {
        "signal_context": {
            "signal_id": "news_inactive_poison_1",
            "ticker_a": "KO",
            "ticker_b": "PEP",
            "z_score": -2.2,
            "sector": "Consumer",
        }
    }
    poison = {
        "active": False,
        "status": "inactive",
        "veto": True,
        "confidence_multiplier": 0.1,
        "materiality": 0.99,
        "reasoning": "poisoned inactive news veto",
    }
    patches = _orchestrator_patches(news_return=poison)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
            patches[6], patches[7], patches[8], patches[9], patches[10]:
        state = await orchestrator.ainvoke(input_data)

    assert state["final_confidence"] > 0.0
    assert "poisoned" not in state["final_verdict"].lower()
