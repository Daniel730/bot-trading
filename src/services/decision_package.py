"""Decision Package — durable "why" artifact for every trade (fund-style).

Not only *what* happened (fills), but *why* (features, risk checks, versions).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from src.services.trade_provenance import build_provenance

logger = logging.getLogger(__name__)

DEFAULT_PACKAGE_DIR = Path("data/decision_packages")


def build_decision_package(
    *,
    trade_id: Optional[str] = None,
    signal_id: Optional[str] = None,
    timestamp: Optional[str] = None,
    provenance: Optional[Mapping[str, Any]] = None,
    market_snapshot: Optional[Mapping[str, Any]] = None,
    feature_vector: Optional[Mapping[str, Any]] = None,
    signal: Optional[Mapping[str, Any]] = None,
    risk_checks: Optional[Mapping[str, Any]] = None,
    broker_state: Optional[Mapping[str, Any]] = None,
    decision: Optional[Mapping[str, Any]] = None,
    execution_result: Optional[Mapping[str, Any]] = None,
    agent_reasoning: Optional[list] = None,
    trade_journal: Optional[Mapping[str, Any]] = None,
    legs: Optional[list] = None,
    extras: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    prov = dict(provenance or build_provenance(features=feature_vector))
    package = {
        "schema": "decision_package/v1",
        "trade_id": trade_id,
        "signal_id": signal_id,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "git_commit": prov.get("git_commit"),
        "strategy_version": prov.get("strategy_version"),
        "risk_version": prov.get("risk_version"),
        "feature_version": prov.get("feature_version"),
        "model_version": prov.get("model_version"),
        "config_hash": prov.get("config_hash"),
        "feature_hash": prov.get("feature_hash"),
        "market_snapshot": dict(market_snapshot or {}),
        "feature_vector": dict(feature_vector or {}),
        "signal": dict(signal or {}),
        "risk_checks": dict(risk_checks or {}),
        "broker_state": dict(broker_state or {}),
        "decision": dict(decision or {}),
        "execution_result": dict(execution_result or {}),
        "agent_reasoning": list(agent_reasoning or []),
        "trade_journal": dict(trade_journal or {}) if trade_journal else None,
        "legs": list(legs or []),
        "provenance": prov,
    }
    if extras:
        package["extras"] = dict(extras)
    return package


def write_decision_package(
    package: Mapping[str, Any],
    *,
    out_dir: str | Path = DEFAULT_PACKAGE_DIR,
) -> Path:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    sid = package.get("signal_id") or package.get("trade_id") or "unknown"
    ts = (package.get("timestamp") or "").replace(":", "").replace("+", "_")[:20]
    path = root / f"decision_{sid}_{ts or 'now'}.json"
    path.write_text(json.dumps(package, indent=2, default=str, sort_keys=True))
    logger.info("Decision package written: %s", path)
    return path


def decision_package_from_reconstruction(pack: Mapping[str, Any]) -> dict[str, Any]:
    """Lift a reconstruct_trade() result into the canonical Decision Package shape."""
    legs = list(pack.get("legs") or [])
    trade_id = legs[0]["id"] if legs else None
    meta0 = (legs[0].get("metadata") if legs else {}) or {}
    signal_block = {
        "signal_id": pack.get("query", {}).get("signal_id"),
        "statuses": [leg.get("status") for leg in legs],
        "tickers": [leg.get("ticker") for leg in legs],
        "sides": [leg.get("side") for leg in legs],
    }
    decision_block = {
        "verdict": meta0.get("decision_verdict") or meta0.get("orchestrator_verdict"),
        "confidence": meta0.get("confidence"),
        "z_score": meta0.get("z_score") or meta0.get("entry_zscore"),
    }
    risk_block = {
        "capital_halt": meta0.get("capital_halt"),
        "live_readiness": meta0.get("live_readiness"),
        "lane_snapshot": meta0.get("lane_snapshot"),
    }
    feature_vector = {
        "z_score": decision_block.get("z_score"),
        "confidence": decision_block.get("confidence"),
        "hedge_ratio": meta0.get("hedge_ratio"),
    }
    return build_decision_package(
        trade_id=trade_id,
        signal_id=pack.get("query", {}).get("signal_id"),
        timestamp=legs[0].get("execution_timestamp") if legs else None,
        provenance=pack.get("provenance"),
        market_snapshot={"note": "Prices at decision live in feature_vector / legs"},
        feature_vector=feature_vector,
        signal=signal_block,
        risk_checks=risk_block,
        broker_state={"intents": pack.get("execution_intents")},
        decision=decision_block,
        execution_result={"legs": legs},
        agent_reasoning=pack.get("agent_reasoning"),
        trade_journal=pack.get("trade_journal"),
        legs=legs,
        extras={
            "incident_packs": pack.get("incident_packs"),
            "runtime_provenance_now": pack.get("runtime_provenance_now"),
            "reconstruction_notes": pack.get("reconstruction_notes"),
        },
    )
