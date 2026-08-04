"""Trade provenance — version stamps for forensic reconstruction (Phase-5 ops).

Every broker/shadow ledger row should carry enough identity to answer:
  which commit, config, strategy, risk model, and feature set produced it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional

from src.config import settings

logger = logging.getLogger(__name__)

STRATEGY_VERSION = "pair-arb-kalman-v1"
RISK_VERSION = "capital-halt-equity-hwm-v1"
FEATURE_VERSION = "zscore-kalman-orchestrator-v1"
MODEL_VERSION = "ensemble-mab-v1"

# Settings keys that materially affect trade decisions (exclude secrets).
_CONFIG_HASH_KEYS = (
    "PAPER_TRADING",
    "DEV_MODE",
    "LIVE_CAPITAL_DANGER",
    "BROKERAGE_PROVIDER",
    "ALPACA_BASE_URL",
    "MONITOR_ENTRY_ZSCORE",
    "MONITOR_EXIT_ZSCORE",
    "MONITOR_STOP_ZSCORE",
    "MAX_DRAWDOWN",
    "MAX_OPEN_PAIRS",
    "MAX_ALLOCATION_PERCENTAGE",
    "ALPACA_BUDGET_USD",
    "BLOCK_SHARED_LEG_OPENS",
    "KALMAN_DELTA",
    "APPROVAL_THRESHOLD",
    "ORCH_AGENT_CONFIDENCE_THRESHOLD",
    "FINANCIAL_KILL_SWITCH_PCT",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def git_commit_sha() -> str:
    env = (os.getenv("GIT_COMMIT") or os.getenv("IMAGE_TAG") or os.getenv("SOURCE_COMMIT") or "").strip()
    if env and env.lower() not in {"latest", "unknown"}:
        return env[:40]
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_repo_root()),
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return out.decode().strip()[:40]
    except Exception:  # noqa: BLE001
        return "unknown"


def config_fingerprint(extra: Optional[Mapping[str, Any]] = None) -> str:
    payload: dict[str, Any] = {}
    for key in _CONFIG_HASH_KEYS:
        payload[key] = getattr(settings, key, None)
    if extra:
        payload.update(dict(extra))
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def feature_hash(features: Optional[Mapping[str, Any]] = None) -> str:
    if not features:
        return hashlib.sha256(FEATURE_VERSION.encode()).hexdigest()[:16]
    encoded = json.dumps(dict(features), sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def build_provenance(
    *,
    features: Optional[Mapping[str, Any]] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Stable provenance block stamped into trade metadata."""
    return {
        "strategy_version": STRATEGY_VERSION,
        "risk_version": RISK_VERSION,
        "feature_version": FEATURE_VERSION,
        "model_version": MODEL_VERSION,
        "git_commit": git_commit_sha(),
        "config_hash": config_fingerprint(),
        "feature_hash": feature_hash(features),
        **(dict(extra) if extra else {}),
    }


def stamp_provenance(
    metadata: Optional[Mapping[str, Any]],
    *,
    features: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    meta = dict(metadata) if isinstance(metadata, Mapping) else {}
    # Do not overwrite an existing provenance block (replay / attach paths).
    if isinstance(meta.get("provenance"), dict) and meta["provenance"].get("git_commit"):
        return meta
    meta["provenance"] = build_provenance(features=features)
    return meta
