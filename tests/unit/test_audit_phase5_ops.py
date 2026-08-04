"""Phase-5 operational foundations: provenance, replay, severity divergence, acceptance."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.services.decision_package import build_decision_package, decision_package_from_reconstruction
from src.services.execution_lane import stamp_trade_metadata
from src.services.limited_live_kill import evaluate_limited_live_kill
from src.services.shadow_live_divergence import (
    DivergenceSeverity,
    ShadowLiveDivergenceMonitor,
    classify_divergence_kind,
)
from src.services.strategy_acceptance import evaluate_strategy_report, evaluate_strategy_report_file
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


def test_config_fingerprint_stable():
    assert config_fingerprint() == config_fingerprint()


def test_stamp_provenance_idempotent():
    meta = stamp_provenance({})
    first = dict(meta["provenance"])
    assert stamp_provenance(meta)["provenance"]["git_commit"] == first["git_commit"]


def test_stamp_trade_metadata_includes_provenance():
    meta = stamp_trade_metadata({"note": "x"}, execution_lane="LIVE", broker_paper_trading=False)
    assert meta["provenance"]["strategy_version"]


def test_decision_divergence_is_critical_not_info():
    mon = ShadowLiveDivergenceMonitor()
    mon.record_live(pair_id="A_B", decision="EXECUTE", confidence=0.9, signal_id="s1")
    mon.record_shadow(pair_id="A_B", decision="SKIP", confidence=0.2, signal_id="s1")
    events = mon.recent()
    assert len(events) == 1
    assert events[0]["reason"] == "decision_divergence"
    assert events[0]["severity"] == "CRITICAL"


def test_info_divergences_do_not_kill_policy(monkeypatch):
    mon = ShadowLiveDivergenceMonitor()
    mon.record_state_divergence(
        pair_id="A_B",
        kind="timestamp_skew",
        live_value="t1",
        shadow_value="t2",
        timestamp_skew_ms=200,
    )
    assert mon.severity_counts()["INFO"] == 1
    assert mon.highest_severity() == "INFO"


def test_fatal_position_mismatch():
    mon = ShadowLiveDivergenceMonitor()
    mon.record_state_divergence(
        pair_id="A_B",
        kind="open_position_mismatch",
        live_value={"qty": 1},
        shadow_value={"qty": 0},
    )
    assert mon.highest_severity() == "FATAL"


def test_classify_timestamp_skew_bands():
    assert classify_divergence_kind(kind="timestamp_skew", timestamp_skew_ms=100) == DivergenceSeverity.INFO
    assert classify_divergence_kind(kind="timestamp_skew", timestamp_skew_ms=1000) == DivergenceSeverity.WARNING
    assert classify_divergence_kind(kind="timestamp_skew", timestamp_skew_ms=9000) == DivergenceSeverity.CRITICAL


@pytest.mark.asyncio
async def test_limited_live_kill_on_reconcile_fails():
    ps = AsyncMock()
    ps.get_system_state = AsyncMock(return_value="5")
    result = await evaluate_limited_live_kill(persistence_service=ps)
    assert result["kill"] is True
    assert result["reason"] == "reconcile_failures_exceeded"


@pytest.mark.asyncio
async def test_limited_live_kill_ignores_info_pile():
    """Many INFO events must not stop the bot (replaces old count>=10 rule)."""
    from src.services import shadow_live_divergence as sld

    mon = ShadowLiveDivergenceMonitor()
    for i in range(20):
        mon.record_state_divergence(
            pair_id=f"P{i}",
            kind="timestamp_skew",
            live_value=i,
            shadow_value=i + 1,
            timestamp_skew_ms=100,
        )
    monkey_mon = mon
    # Patch module singleton used by kill evaluator
    original = sld.shadow_live_divergence_monitor
    sld.shadow_live_divergence_monitor = monkey_mon
    try:
        ps = AsyncMock()
        ps.get_system_state = AsyncMock(return_value="0")
        result = await evaluate_limited_live_kill(persistence_service=ps)
        assert result["kill"] is False
    finally:
        sld.shadow_live_divergence_monitor = original


@pytest.mark.asyncio
async def test_limited_live_kill_on_critical_divergence():
    from src.services import shadow_live_divergence as sld

    mon = ShadowLiveDivergenceMonitor()
    mon.record_live(pair_id="A_B", decision="EXECUTE", confidence=0.9)
    mon.record_shadow(pair_id="A_B", decision="SKIP", confidence=0.1)
    original = sld.shadow_live_divergence_monitor
    sld.shadow_live_divergence_monitor = mon
    try:
        ps = AsyncMock()
        ps.get_system_state = AsyncMock(return_value="0")
        result = await evaluate_limited_live_kill(persistence_service=ps)
        assert result["kill"] is True
        assert result["severity"] == "CRITICAL"
        assert result["flatten_recommended"] is False
    finally:
        sld.shadow_live_divergence_monitor = original


@pytest.mark.asyncio
async def test_limited_live_fatal_recommends_flatten():
    from src.services import shadow_live_divergence as sld

    mon = ShadowLiveDivergenceMonitor()
    mon.record_state_divergence(
        pair_id="A_B",
        kind="quantity_mismatch",
        live_value=10,
        shadow_value=0,
    )
    original = sld.shadow_live_divergence_monitor
    sld.shadow_live_divergence_monitor = mon
    try:
        ps = AsyncMock()
        ps.get_system_state = AsyncMock(return_value="0")
        result = await evaluate_limited_live_kill(persistence_service=ps)
        assert result["kill"] is True
        assert result["severity"] == "FATAL"
        assert result["flatten_recommended"] is True
    finally:
        sld.shadow_live_divergence_monitor = original


def test_decision_package_schema_fields():
    pkg = build_decision_package(
        trade_id="t1",
        signal_id="s1",
        feature_vector={"z": 2.0},
        decision={"verdict": "EXECUTE"},
    )
    assert pkg["schema"] == "decision_package/v1"
    assert pkg["git_commit"]
    assert pkg["feature_vector"]["z"] == 2.0


def test_decision_package_from_reconstruction_shape():
    fake = {
        "query": {"signal_id": "s1"},
        "provenance": build_provenance(),
        "legs": [
            {
                "id": "leg1",
                "ticker": "AAPL",
                "side": "BUY",
                "status": "OPEN",
                "execution_timestamp": "2026-08-04T00:00:00Z",
                "metadata": {"z_score": 2.2, "confidence": 0.7},
            }
        ],
        "agent_reasoning": [],
        "trade_journal": None,
        "execution_intents": [],
        "incident_packs": [],
        "reconstruction_notes": [],
    }
    pkg = decision_package_from_reconstruction(fake)
    assert pkg["signal_id"] == "s1"
    assert pkg["feature_vector"]["z_score"] == 2.2


def test_strategy_acceptance_sample_report_passes():
    path = Path("research/examples/sample_strategy_report.json")
    result = evaluate_strategy_report_file(path)
    assert result.accepted is True


def test_strategy_acceptance_rejects_overfit_fragile():
    report = {
        "sharpe": 2.0,
        "sortino": 2.5,
        "profit_factor": 2.0,
        "max_drawdown": 0.1,
        "expectancy": 1.0,
        "n_trades": 100,
        "costs_modeled": True,
        "walk_forward_completed": True,
        "oos_completed": True,
        "robustness": {"param_shock_pm_10pct": {"base_sharpe": 2.0, "worst_sharpe": 0.2}},
        "search_space": {"combinations_tested": 10, "multiple_testing_corrected": True},
    }
    result = evaluate_strategy_report(report)
    assert result.accepted is False
    assert any("robustness" in f for f in result.failures)
