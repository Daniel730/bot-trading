"""Phase-5 operational foundations: provenance, replay, shadow divergence, kill criteria."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from src.services.execution_lane import stamp_trade_metadata
from src.services.limited_live_kill import evaluate_limited_live_kill
from src.services.shadow_live_divergence import ShadowLiveDivergenceMonitor
from src.services.trade_provenance import (
    STRATEGY_VERSION,
    build_provenance,
    config_fingerprint,
    stamp_provenance,
)


def test_provenance_block_has_required_fields():
    p = build_provenance(features={"z": 2.1})
    assert p["strategy_version"] == STRATEGY_VERSION
    assert p["git_commit"]
    assert p["config_hash"]
    assert p["feature_hash"]
    assert p["risk_version"]
    assert p["model_version"]


def test_config_fingerprint_stable():
    a = config_fingerprint()
    b = config_fingerprint()
    assert a == b
    assert len(a) == 16


def test_stamp_provenance_idempotent():
    meta = stamp_provenance({})
    first = dict(meta["provenance"])
    meta2 = stamp_provenance(meta)
    assert meta2["provenance"]["git_commit"] == first["git_commit"]


def test_stamp_trade_metadata_includes_provenance():
    meta = stamp_trade_metadata(
        {"note": "x"},
        execution_lane="LIVE",
        broker_paper_trading=False,
    )
    assert meta["execution_lane"] == "LIVE"
    assert "provenance" in meta
    assert meta["provenance"]["strategy_version"]


def test_shadow_live_decision_divergence_alerts():
    mon = ShadowLiveDivergenceMonitor()
    mon.record_live(pair_id="A_B", decision="EXECUTE", confidence=0.9, signal_id="s1")
    mon.record_shadow(pair_id="A_B", decision="SKIP", confidence=0.2, signal_id="s1")
    events = mon.recent()
    assert len(events) == 1
    assert events[0]["reason"] == "decision_divergence"


def test_shadow_live_matching_decisions_no_alert():
    mon = ShadowLiveDivergenceMonitor()
    mon.record_live(pair_id="A_B", decision="EXECUTE", confidence=0.80)
    mon.record_shadow(pair_id="A_B", decision="EXECUTE", confidence=0.82)
    assert mon.divergence_count() == 0


@pytest.mark.asyncio
async def test_limited_live_kill_on_reconcile_fails():
    ps = AsyncMock()
    ps.get_system_state = AsyncMock(return_value="5")
    result = await evaluate_limited_live_kill(persistence_service=ps, divergence_count=0)
    assert result["kill"] is True
    assert result["reason"] == "reconcile_failures_exceeded"


@pytest.mark.asyncio
async def test_limited_live_kill_on_divergences():
    ps = AsyncMock()
    ps.get_system_state = AsyncMock(return_value="0")
    result = await evaluate_limited_live_kill(persistence_service=ps, divergence_count=99)
    assert result["kill"] is True
    assert result["reason"] == "shadow_live_divergences_exceeded"
