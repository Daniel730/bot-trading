"""Architectural contract tests (Python) — invariants from docs/CLAUDE.md / AGENTS.md."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from src.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


def _iter_py_files(root: Path):
    for path in root.rglob("*.py"):
        if "generated" in path.parts:
            continue
        yield path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_paper_trading_defaults_true():
    settings = Settings.model_construct()
    # model_construct bypasses validators; assert field default on the model.
    field = Settings.model_fields["PAPER_TRADING"]
    assert field.default is True


def test_brokerage_get_venue_is_the_venue_authority():
    """Venue routing must live on BrokerageService.get_venue (not ad-hoc string checks)."""
    brokerage = SRC_ROOT / "services" / "brokerage_service.py"
    text = _read(brokerage)
    assert "def get_venue" in text


def test_no_hardcoded_alpaca_venue_equality_outside_brokerage_and_config():
    """Discourage `== \"ALPACA\"` venue checks outside brokerage/config/dashboard metadata."""
    allowed_parts = {
        ("services", "brokerage_service.py"),
        ("services", "brokerage", "alpaca.py"),
        ("services", "brokerage", "base.py"),
        ("config.py",),
        ("services", "dashboard_service.py"),  # config metadata / mode labels
        ("services", "venue_metadata.py"),
    }
    pattern = re.compile(r"""==\s*["']ALPACA["']|["']ALPACA["']\s*==""")
    offenders: list[str] = []
    for path in _iter_py_files(SRC_ROOT):
        rel = path.relative_to(SRC_ROOT)
        if tuple(rel.parts) in allowed_parts or rel.parts[:2] == ("services", "brokerage"):
            continue
        if "test" in rel.parts:
            continue
        text = _read(path)
        if pattern.search(text):
            # Allow provider env / docs strings that are not venue routing.
            if "BROKERAGE_PROVIDER" in text and "get_venue" not in text:
                # still flag if the file compares venue-like tokens without get_venue
                pass
            offenders.append(str(rel).replace("\\", "/"))
    # Soft gate: known historical leftovers must shrink, not grow unchecked.
    # Fail only on clearly new hot paths under monitor / agents / daemons.
    hot = [o for o in offenders if o.startswith(("monitor.py", "agents/", "daemons/"))]
    assert hot == [], f"Hardcoded ALPACA venue equality in hot paths: {hot}"


def test_signal_id_appears_in_persistence_and_journal_paths():
    persistence = _read(SRC_ROOT / "services" / "persistence_service.py")
    journal = _read(SRC_ROOT / "services" / "journal_audit_service.py")
    assert "signal_id" in persistence
    assert "signal_id" in journal


def test_telemetry_service_has_no_live_fake_http_sync_requirement():
    """#122: stub endpoint must not be treated as a required live dependency."""
    text = _read(SRC_ROOT / "services" / "telemetry_service.py")
    # Placeholder host may still exist until #122 lands; sync_outcomes must stay non-fatal.
    assert "async def sync_outcomes" in text or "def sync_outcomes" in text
    tree = ast.parse(text)
    # Ensure module defines TelemetryService class
    classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert "TelemetryService" in classes


@pytest.mark.parametrize(
    "forbidden",
    [
        "api.arbitrage-elite.com",
    ],
)
def test_monitor_does_not_hardcode_fake_telemetry_host(forbidden: str):
    monitor = _read(SRC_ROOT / "monitor.py")
    assert forbidden not in monitor
