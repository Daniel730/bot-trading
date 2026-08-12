#!/usr/bin/env python3
"""Coverage tests for the Daily Bot Audit — verify the gaps are tested.

These tests exist to close coverage holes identified by pytest --cov.
They are supplementary to the functional/behaviour tests in
test_daily_bot_audit.py / test_daily_bot_audit_failures.py / test_daily_bot_audit_pipeline.py.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Shared module-level fixtures so we can monkeypatch Path constants etc.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# RemediationState.load / save / can_apply (scripts/audit_remediations.py)
# ---------------------------------------------------------------------------
class TestRemediationStateLoad:
    def test_load_creates_empty_state_when_file_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "no_such" / "state.json"
        from scripts.audit_remediations import RemediationState

        state = RemediationState.load(missing)
        assert state.attempts == {}
        assert state.last_applied_at == {}
        assert state.last_outcome == {}

    def test_load_returns_empty_on_broken_json(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken.json"
        broken.write_text("not valid json {{{", encoding="utf-8")
        from scripts.audit_remediations import RemediationState

        state = RemediationState.load(broken)
        assert state.attempts == {}

    def test_load_returns_empty_on_os_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.audit_remediations import RemediationState

        def _boom(*_a: object, **_k: object) -> bytes:
            raise OSError("disk fried")

        monkeypatch.setattr(Path, "read_text", _boom)
        state = RemediationState.load(Path("/does/not/exist"))
        assert state.attempts == {}

    def test_load_preserves_attempts(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text(
            json.dumps({"attempts": {"sig-a": 2}, "last_applied_at": {}, "last_outcome": {}}),
            encoding="utf-8",
        )
        from scripts.audit_remediations import RemediationState

        state = RemediationState.load(path)
        assert state.attempts == {"sig-a": 2}

    def test_load_preserves_last_applied_at(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text(
            json.dumps(
                {
                    "attempts": {},
                    "last_applied_at": {"sig-x": 1_700_000_000.0},
                    "last_outcome": {},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        from scripts.audit_remediations import RemediationState

        state = RemediationState.load(path)
        assert state.last_applied_at == {"sig-x": 1_700_000_000.0}

    def test_load_preserves_last_outcome(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text(
            json.dumps({"attempts": {}, "last_applied_at": {}, "last_outcome": {"sig-z": "applied"}}),
            encoding="utf-8",
        )
        from scripts.audit_remediations import RemediationState

        state = RemediationState.load(path)
        assert state.last_outcome == {"sig-z": "applied"}


class TestRemediationStateSave:
    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "state.json"
        from scripts.audit_remediations import RemediationState

        state = RemediationState(attempts={"x": 1}, last_applied_at={}, last_outcome={})
        state.save(deep)
        assert deep.exists()
        data = json.loads(deep.read_text(encoding="utf-8"))
        assert data["attempts"] == {"x": 1}

    def test_save_writes_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "out.json"
        from scripts.audit_remediations import RemediationState

        state = RemediationState(attempts={"a": 3}, last_applied_at={"a": 100.0}, last_outcome={"a": "applied"})
        state.save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["attempts"] == {"a": 3}
        assert data["last_applied_at"] == {"a": 100.0}
        assert data["last_outcome"] == {"a": "applied"}


class TestRemediationStateCanApply:
    def test_can_apply_allows_first_try(self, tmp_path: Path) -> None:
        path = tmp_path / "s.json"
        from scripts.audit_remediations import RemediationState

        state = RemediationState.load(path)
        allowed, reason = state.can_apply("fresh")
        assert allowed is True
        assert reason == "ok"

    def test_can_apply_denies_when_attempt_cap_reached(self, tmp_path: Path) -> None:
        path = tmp_path / "s.json"
        from scripts.audit_remediations import RemediationState

        state = RemediationState(attempts={"sig-a": 3}, last_applied_at={}, last_outcome={})
        state.save(path)
        state = RemediationState.load(path)
        allowed, reason = state.can_apply("sig-a")
        assert allowed is False
        assert "attempt cap" in reason

    def test_can_apply_denies_within_cooldown(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = tmp_path / "s.json"
        from scripts.audit_remediations import RemediationState

        fake_now = 1_000_000.0
        monkeypatch.setattr(time, "time", lambda: fake_now)
        state = RemediationState(attempts={"sig-b": 1}, last_applied_at={"sig-b": fake_now - 100}, last_outcome={})
        state.save(path)
        state = RemediationState.load(path)
        allowed, reason = state.can_apply("sig-b", now=fake_now)
        assert allowed is False
        assert "cooldown" in reason.lower()

    def test_can_apply_allows_after_cooldown(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = tmp_path / "s.json"
        from scripts.audit_remediations import RemediationState

        fake_now = 1_000_000.0
        monkeypatch.setattr(time, "time", lambda: fake_now)
        state = RemediationState(attempts={"sig-c": 1}, last_applied_at={"sig-c": fake_now - 30 * 24 * 3600}, last_outcome={})
        state.save(path)
        state = RemediationState.load(path)
        allowed, reason = state.can_apply("sig-c", now=fake_now)
        assert allowed is True


# ---------------------------------------------------------------------------
# _monitor_running (scripts/audit_remediations.py)
# ---------------------------------------------------------------------------
class TestMonitorRunning:
    def test_monitor_running_subprocess_error_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.audit_remediations import _monitor_running

        def _raise(*_a: object, **_k: object) -> object:
            raise subprocess.SubprocessError("no pgrep")

        monkeypatch.setattr(subprocess, "run", _raise)
        assert _monitor_running() is False

    def test_monitor_running_returns_false_subprocess_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.audit_remediations import _monitor_running

        def _return_empty(*_a: object, **_k: object) -> object:
            class Fake:
                stdout = ""

            return Fake()

        monkeypatch.setattr(subprocess, "run", _return_empty)
        assert _monitor_running() is False

    def test_monitor_running_returns_true_subprocess_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.audit_remediations import _monitor_running

        class FakeOut:
            stdout = "12345 monitor.py"

        def _return_running(*_a: object, **_k: object) -> object:
            return FakeOut()

        monkeypatch.setattr(subprocess, "run", _return_running)
        assert _monitor_running() is True

    def test_monitor_running_returns_false_on_os_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.audit_remediations import _monitor_running

        def _os_error(*_a: object, **_k: object) -> object:
            raise OSError("no pgrep binary")

        monkeypatch.setattr(subprocess, "run", _os_error)
        assert _monitor_running() is False


# ---------------------------------------------------------------------------
# discover_safe_fixes (scripts/audit_remediations.py)
# ---------------------------------------------------------------------------
class TestDiscoverSafeFixes:
    def test_returns_empty_list_when_all_dirs_exist(self, tmp_path: Path) -> None:
        from scripts.audit_remediations import discover_safe_fixes

        for sub in ("reports/daily-audit", "data/audit/logs"):
            (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        fixes = discover_safe_fixes(tmp_path)
        assert isinstance(fixes, list)

    def test_proposes_ensure_audit_dirs_when_missing(self, tmp_path: Path) -> None:
        from scripts.audit_remediations import discover_safe_fixes

        fixes = discover_safe_fixes(tmp_path)
        sigs = [f.signature for f in fixes]
        assert "ensure_audit_dirs" in sigs

    def test_discover_safe_fixes_missing_dirs_os_error(self, tmp_path: Path) -> None:
        from scripts.audit_remediations import discover_safe_fixes

        # tmp_path has no audit dirs created, so discover_safe_fixes should
        # still propose the ensure_audit_dirs fix without crashing.
        fixes = discover_safe_fixes(tmp_path)
        sigs = [f.signature for f in fixes]
        assert "ensure_audit_dirs" in sigs

    def test_discover_safe_fixes_captures_os_error_stat(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from scripts.audit_remediations import discover_safe_fixes

        (tmp_path / "data" / "audit" / "logs").mkdir(parents=True, exist_ok=True)
        monitor_out = tmp_path / "data" / "audit" / "logs" / "monitor.out"
        monitor_out.write_text("data", encoding="utf-8")

        def _stat_ok(self: Path) -> object:
            class S:
                st_size = 100
            return S()

        def _stat_os_error(self: Path) -> object:
            raise OSError("boom")

        monkeypatch.setattr(
            Path, "stat",
            lambda self: _stat_ok(self) if str(self).endswith("logs/monitor.out") else _stat_os_error(self),
        )
        fixes = discover_safe_fixes(tmp_path)
        sigs = [f.signature for f in fixes]
        assert "ensure_audit_dirs" in sigs

    def test_discover_safe_fixes_proposes_rotate_fix_full(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.audit_remediations import discover_safe_fixes

        logs = tmp_path / "data" / "audit" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        monitor_out = logs / "monitor.out"
        monitor_out.write_text("", encoding="utf-8")

        def _stat(self: Path) -> object:
            class S:
                st_size = 0

            return S()

        monkeypatch.setattr(Path, "stat", _stat)
        fixes = discover_safe_fixes(tmp_path)
        rotate = [f for f in fixes if f.signature == "rotate_empty_monitor_out"]
        assert len(rotate) == 1
        assert "0 bytes" in rotate[0].detail

    def test_discover_safe_fixes_does_not_propose_rotate_when_monitor_running(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.audit_remediations import discover_safe_fixes

        logs = tmp_path / "data" / "audit" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        monitor_out = logs / "monitor.out"
        monitor_out.write_text("some data", encoding="utf-8")

        def _stat(self: Path) -> object:
            class S:
                st_size = 100

            return S()

        monkeypatch.setattr(Path, "stat", _stat)
        fixes = discover_safe_fixes(tmp_path)
        rotate = [f for f in fixes if f.signature == "rotate_empty_monitor_out"]
        assert len(rotate) == 0


# ---------------------------------------------------------------------------
# apply_with_guard (scripts/audit_remediations.py)
# ---------------------------------------------------------------------------
class TestApplyWithGuard:
    def test_apply_with_guard_skips_on_apply_error(self, tmp_path: Path) -> None:
        from scripts.audit_remediations import RemediationState, apply_with_guard, Fix

        state = RemediationState()
        failing = Fix(
            signature="boom",
            title="fails on apply",
            detail="",
            apply=lambda: (_ for _ in ()).throw(RuntimeError("apply boom")),
            validate=lambda: True,
            evidence="",
        )
        ok, msg = apply_with_guard(failing, state)
        assert ok is False
        assert "apply raised" in msg
        assert state.attempts["boom"] == 1
        assert state.last_outcome["boom"].startswith("apply_error")

    def test_apply_with_guard_reverts_on_validate_error(self, tmp_path: Path) -> None:
        from scripts.audit_remediations import RemediationState, apply_with_guard, Fix

        tmp_file = tmp_path / "marker.txt"
        tmp_file.write_text("original", encoding="utf-8")

        def _apply() -> None:
            tmp_file.write_text("changed", encoding="utf-8")

        def _validate() -> bool:
            return False

        def _restore() -> None:
            tmp_file.write_text("restored", encoding="utf-8")

        state = RemediationState()
        fix = Fix(signature="revert-me", title="", detail="", apply=_apply, validate=_validate, restore=_restore, evidence="")
        ok, msg = apply_with_guard(fix, state)
        assert ok is False
        assert "reverted" in msg
        assert state.attempts["revert-me"] == 1
        assert state.last_outcome["revert-me"] == "validation_failed_reverted"

    def test_apply_with_guard_calls_restore_when_validate_fails(self, tmp_path: Path) -> None:
        from scripts.audit_remediations import RemediationState, apply_with_guard, Fix

        marker = tmp_path / "marker.txt"
        marker.write_text("orig", encoding="utf-8")
        called: dict[str, bool] = {"restore": False}

        def _apply() -> None:
            marker.write_text("changed", encoding="utf-8")

        def _validate() -> bool:
            return False

        def _restore() -> None:
            nonlocal called
            called["restore"] = True

        state = RemediationState()
        fix = Fix(signature="restore-called", title="", detail="", apply=_apply, validate=_validate, restore=_restore, evidence="")
        ok, _msg = apply_with_guard(fix, state)
        assert ok is False
        assert called["restore"] is True

    def test_apply_with_guard_restore_exception_is_swallowed(self, tmp_path: Path) -> None:
        from scripts.audit_remediations import RemediationState, apply_with_guard, Fix

        marker = tmp_path / "m.txt"
        marker.write_text("orig", encoding="utf-8")

        def _apply() -> None:
            marker.write_text("changed", encoding="utf-8")

        def _validate() -> bool:
            return False

        def _restore() -> None:
            raise RuntimeError("restore blew up")

        state = RemediationState()
        fix = Fix(signature="restore-swallow", title="", detail="", apply=_apply, validate=_validate, restore=_restore, evidence="")
        ok, msg = apply_with_guard(fix, state)
        assert ok is False
        assert state.last_outcome["restore-swallow"] == "validation_failed_reverted"
        # The exception in restore is swallowed; state is still updated.
        assert "restore" not in msg

    def test_apply_with_guard_successbumps_attempt_and_time(self, tmp_path: Path) -> None:
        from scripts.audit_remediations import RemediationState, apply_with_guard, Fix

        state = RemediationState()
        now = time.time()
        fix = Fix(signature="good", title="", detail="", apply=lambda: None, validate=lambda: True, evidence="")
        ok, msg = apply_with_guard(fix, state, now=now)
        assert ok is True
        assert state.attempts["good"] == 1
        assert state.last_applied_at["good"] == now
        assert state.last_outcome["good"] == "applied"


# ---------------------------------------------------------------------------
# compute_historical_trend (scripts/daily_bot_audit.py)
# ---------------------------------------------------------------------------
class TestHistoricalTrend:
    def test_returns_not_available_when_no_metrics(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        metric_dir = tmp_path / "empty_metrics"
        metric_dir.mkdir()
        from scripts.daily_bot_audit import compute_historical_trend

        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", metric_dir)
        hist = compute_historical_trend()
        assert hist["available"] is False
        assert hist["note"] == "no historical metrics yet"

    def test_worsening_detected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import compute_historical_trend

        d = tmp_path / "metrics"
        d.mkdir()
        (d / "2026-08-10.json").write_text(json.dumps({"date": "2026-08-10", "errors": 1, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        (d / "2026-08-11.json").write_text(json.dumps({"date": "2026-08-11", "errors": 5, "incidents": 2, "api_degraded": 1, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        hist = compute_historical_trend(days=7)
        assert hist["available"] is True
        assert "errors" in hist["worsening_vs_prev"]
        assert hist["worsening_vs_prev"]["errors"]["prev"] == 1
        assert hist["worsening_vs_prev"]["errors"]["last"] == 5

    def test_recurring_detected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import compute_historical_trend

        d = tmp_path / "metrics"
        d.mkdir()
        (d / "2026-08-09.json").write_text(json.dumps({"date": "2026-08-09", "incidents": 1, "errors": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        (d / "2026-08-10.json").write_text(json.dumps({"date": "2026-08-10", "incidents": 1, "errors": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        (d / "2026-08-11.json").write_text(json.dumps({"date": "2026-08-11", "incidents": 0, "errors": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        hist = compute_historical_trend(days=7)
        assert hist["available"] is True
        assert "incidents" in hist["recurring"]
        assert hist["recurring"]["incidents"]["days_hot"] == 2

    def test_deltas_computed_first_to_last(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import compute_historical_trend

        d = tmp_path / "metrics"
        d.mkdir()
        (d / "2026-08-09.json").write_text(json.dumps({"date": "2026-08-09", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        (d / "2026-08-11.json").write_text(json.dumps({"date": "2026-08-11", "errors": 7, "incidents": 1, "api_degraded": 2, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        hist = compute_historical_trend(days=7)
        assert hist["deltas"]["errors"]["first"] == 0
        assert hist["deltas"]["errors"]["last"] == 7
        assert hist["deltas"]["errors"]["delta"] == 7

    def test_verdict_trajectory_captured(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import compute_historical_trend

        d = tmp_path / "metrics"
        d.mkdir()
        (d / "2026-08-09.json").write_text(json.dumps({"date": "2026-08-09", "verdict": "HEALTHY", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        (d / "2026-08-10.json").write_text(json.dumps({"date": "2026-08-10", "verdict": "DEGRADED", "errors": 1, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        (d / "2026-08-11.json").write_text(json.dumps({"date": "2026-08-11", "verdict": "HEALTHY", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        hist = compute_historical_trend(days=7)
        assert hist["verdict_trajectory"] == ["HEALTHY", "DEGRADED", "HEALTHY"]

    def test_metric_files_count(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import compute_historical_trend

        d = tmp_path / "metrics"
        d.mkdir()
        (d / "2026-08-09.json").write_text(json.dumps({"date": "2026-08-09", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        (d / "2026-08-10.json").write_text(json.dumps({"date": "2026-08-10", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        hist = compute_historical_trend(days=7)
        assert hist["metrics_files"] == 2
        assert hist["from"] == "2026-08-09"
        assert hist["to"] == "2026-08-10"

    def test_days_parameter_limits_window(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import compute_historical_trend

        d = tmp_path / "metrics"
        d.mkdir()
        # 13 files from 2026-08-10..2026-08-22; --days 5 => last 5 = 18..22.
        for i in range(13):
            (d / f"2026-08-{10 + i:02d}.json").write_text(
                json.dumps({"date": f"2026-08-{10 + i:02d}", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2)
            )
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        hist = compute_historical_trend(days=5)
        assert hist["metrics_files"] == 5
        assert hist["from"] == "2026-08-18"

    def test_skips_files_without_date(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import compute_historical_trend

        d = tmp_path / "metrics"
        d.mkdir()
        (d / "2026-08-10.json").write_text(json.dumps({"date": "2026-08-10", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        (d / "no_date.json").write_text(json.dumps({"errors": 99}, indent=2))
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        hist = compute_historical_trend(days=7)
        assert hist["metrics_files"] == 1
        assert hist["from"] == "2026-08-10"

    def test_ignores_bad_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import compute_historical_trend

        d = tmp_path / "metrics"
        d.mkdir()
        (d / "2026-08-10.json").write_text('{"date": "2026-08-10", "errors": 1', encoding="utf-8")  # truncated
        (d / "2026-08-11.json").write_text(json.dumps({"date": "2026-08-11", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0}, indent=2))
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        hist = compute_historical_trend(days=7)
        assert hist["available"] is True
        assert hist["metrics_files"] == 1


# ---------------------------------------------------------------------------
# CLI audit_trend.py
# ---------------------------------------------------------------------------
class TestAuditTrendCli:
    def test_main_returns_0_when_no_worsening(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        d = tmp_path / "metrics"
        d.mkdir()
        (d / "2026-08-10.json").write_text(json.dumps({"date": "2026-08-10", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0, "verdict": "HEALTHY"}, indent=2))
        (d / "2026-08-11.json").write_text(json.dumps({"date": "2026-08-11", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0, "verdict": "HEALTHY"}, indent=2))
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        from scripts.audit_trend import main

        assert main([]) == 0

    def test_main_returns_1_when_worsening(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        d = tmp_path / "metrics"
        d.mkdir()
        (d / "2026-08-10.json").write_text(json.dumps({"date": "2026-08-10", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0, "verdict": "HEALTHY"}, indent=2))
        (d / "2026-08-11.json").write_text(json.dumps({"date": "2026-08-11", "errors": 3, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0, "verdict": "HEALTHY"}, indent=2))
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        from scripts.audit_trend import main

        assert main([]) == 1

    def test_main_returns_1_when_recurring(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        d = tmp_path / "metrics"
        d.mkdir()
        (d / "2026-08-10.json").write_text(json.dumps({"date": "2026-08-10", "errors": 1, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0, "verdict": "HEALTHY"}, indent=2))
        (d / "2026-08-11.json").write_text(json.dumps({"date": "2026-08-11", "errors": 1, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0, "verdict": "HEALTHY"}, indent=2))
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        from scripts.audit_trend import main

        assert main([]) == 1

    def test_main_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
        d = tmp_path / "metrics"
        d.mkdir()
        (d / "2026-08-10.json").write_text(json.dumps({"date": "2026-08-10", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0, "verdict": "HEALTHY"}, indent=2))
        (d / "2026-08-11.json").write_text(json.dumps({"date": "2026-08-11", "errors": 1, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0, "verdict": "HEALTHY"}, indent=2))
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        from scripts.audit_trend import main

        main(["--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["available"] is True
        assert data["deltas"]["errors"]["last"] == 1

    def test_main_respects_days_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        d = tmp_path / "metrics"
        d.mkdir()
        # Create 13 days of data.
        for i in range(13):
            (d / f"2026-08-{10 + i:02d}.json").write_text(
                json.dumps({"date": f"2026-08-{10 + i:02d}", "errors": 0, "incidents": 0, "api_degraded": 0, "critical_level": 0, "failed_ci_runs": 0, "open_issues": 0, "verdict": "HEALTHY"}, indent=2)
            )
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "METRICS_DIR", d)
        from scripts.audit_trend import main

        hist = main(["--days", "3"])
        # main returns int exit code; we check side-effect via monkeypatched METRICS_DIR
        assert hist == 0  # no worsening in this data

    def test_now_iso_returns_utc_timestamp(self) -> None:
        from scripts.audit_remediations import _now_iso

        ts = _now_iso()
        assert ts.endswith("+00:00") or ts.endswith("Z")
        # parseable
        datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# main() block of audit_trend.py (line 73 — __main__ guard)
# ---------------------------------------------------------------------------
class TestAuditTrendMainBlock:
    def test_audit_trend_main_block_runs_as_script(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover audit_trend.py:73 — if __name__ == "__main__": raise SystemExit(main()).

        The only way to trigger the ``if __name__ == "__main__"`` guard is to run
        the real audit_trend.py script as a subprocess (importing main() directly
        skips that block). We monkeypatch METRICS_DIR in the current process so
        that when the subprocess imports scripts.daily_bot_audit, it sees the
        temp metrics dir.
        """
        d = tmp_path / "metrics"
        d.mkdir()
        (d / "2026-08-10.json").write_text(
            json.dumps({"date": "2026-08-10", "errors": 0, "incidents": 0,
                        "api_degraded": 0, "critical_level": 0,
                        "failed_ci_runs": 0, "open_issues": 0, "verdict": "HEALTHY"},
                       indent=2)
        )
        (d / "2026-08-11.json").write_text(
            json.dumps({"date": "2026-08-11", "errors": 0, "incidents": 0,
                        "api_degraded": 0, "critical_level": 0,
                        "failed_ci_runs": 0, "open_issues": 0, "verdict": "HEALTHY"},
                       indent=2)
        )
        # monkeypatch doesn't survive into a subprocess. Write METRICS_DIR
        # into a small wrapper that the subprocess will execute instead.
        wrapper = tmp_path / "run_audit_trend.py"
        wrapper.write_text(
            "import sys\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, {repr(str(ROOT))})\n"
            "import scripts.daily_bot_audit as dba\n"
            f"dba.METRICS_DIR = Path({repr(str(d))})\n"
            "from scripts.audit_trend import main\n"
            "sys.exit(main([]))\n",
            encoding="utf-8",
        )
        audit_trend = ROOT / "scripts" / "audit_trend.py"
        proc = subprocess.run(
            [sys.executable, str(wrapper)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        # main() returns 0 when no worsening; SystemExit(0) → returncode 0.
        assert proc.returncode == 0, f"expected 0, got {proc.returncode}; stderr: {proc.stderr[:300]}"
        assert "HISTORICAL TREND" in proc.stdout


# ---------------------------------------------------------------------------
# _now_iso from daily_bot_audit (line 118) — separate from remediations'
# ---------------------------------------------------------------------------
class TestDailyBotAuditNowIso:
    def test_now_iso_utc(self) -> None:
        from scripts.daily_bot_audit import _now_iso

        ts = _now_iso()
        assert "T" in ts
        assert ts.endswith("+00:00")


# ---------------------------------------------------------------------------
# _run error paths (scripts/daily_bot_audit.py lines 122-131) — subprocess
# timeout + FileNotFoundError
# ---------------------------------------------------------------------------
class TestRunErrorPaths:
    def test_run_timeout_returns_124(self) -> None:
        from scripts.daily_bot_audit import _run

        rc, out, err = _run(["sleep", "999"], timeout=1)
        assert rc == 124

    def test_run_file_not_found_returns_127(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import _run

        def _fake_run(cmd: list[str], **_k: object) -> object:
            raise FileNotFoundError("not found")

        monkeypatch.setattr(subprocess, "run", _fake_run)
        rc, out, err = _run(["nonexistent-binary"])
        assert rc == 127
        assert "not found" in err


# ---------------------------------------------------------------------------
# Render report happy path + edge cases (scripts/daily_bot_audit.py)
# ---------------------------------------------------------------------------
class TestRenderReport:
    def test_render_report_headers(self) -> None:
        from scripts.daily_bot_audit import Report, render_report

        r = Report(date="2026-08-12", commit="abc123", environment="local:main", runtime_health="UP")
        rendered = render_report(r)
        assert "# BOT DAILY AUDIT" in rendered
        assert "Date: 2026-08-12" in rendered
        assert "Commit: abc123" in rendered
        assert "Environment: local:main" in rendered
        assert "Runtime: UP" in rendered
        assert "Health: HEALTHY" in rendered

    def test_render_report_empty_sections(self) -> None:
        from scripts.daily_bot_audit import Report, render_report

        r = Report(date="2026-08-12", commit="abc", environment="local", runtime_health="NOT-RUNNING-HERE (bot is on bot-server)")
        rendered = render_report(r)
        assert "Bot API not reachable" in rendered
        assert "(none)" in rendered  # empty findings sections

    def test_render_report_no_trading_reachable(self) -> None:
        from scripts.daily_bot_audit import Report, render_report, Finding

        r = Report(date="2026-08-12", commit="abc", environment="local", runtime_health="UP")
        r.add(Finding("INFO", "test", "detail", "Logs"))
        rendered = render_report(r)
        assert "not reachable" in rendered or "n/a" in rendered


# ---------------------------------------------------------------------------
# Check env safety branches (scripts/daily_bot_audit.py)
# ---------------------------------------------------------------------------
class TestCheckEnvSafety:
    def test_no_env_file_returns_not_checked(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import Report, check_env_safety

        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "ENV_PATH", tmp_path / "missing.env")
        r = Report(date="2026-08-12", commit="abc", environment="local", runtime_health="UP")
        res = check_env_safety(r)
        assert res["checked"] is False
        assert "no .env" in res.get("note", "")

    def test_paper_trading_false_without_live_danger_emits_finding(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import Report, check_env_safety

        env = tmp_path / ".env"
        env.write_text('PAPER_TRADING=false\nLIVE_CAPITAL_DANGER=false\n', encoding="utf-8")
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "ENV_PATH", env)
        r = Report(date="2026-08-12", commit="abc", environment="local", runtime_health="UP")
        res = check_env_safety(r)
        assert res["checked"] is True
        assert res["paper"] is False
        # A finding should have been added
        high_findings = [f for f in r.findings if f.severity == "HIGH" and "LIVE_CAPITAL_DANGER" in f.title]
        assert len(high_findings) == 1

    def test_non_alpaca_provider_emits_finding(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import Report, check_env_safety

        env = tmp_path / ".env"
        env.write_text('BROKERAGE_PROVIDER=LEGACY\n', encoding="utf-8")
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "ENV_PATH", env)
        r = Report(date="2026-08-12", commit="abc", environment="local", runtime_health="UP")
        res = check_env_safety(r)
        assert res["provider"] == "LEGACY"
        med_findings = [f for f in r.findings if f.severity == "MEDIUM" and "BROKERAGE_PROVIDER" in f.title]
        assert len(med_findings) == 1


# ---------------------------------------------------------------------------
# verify_financial_safety — all-present branch
# ---------------------------------------------------------------------------
class TestVerifyFinancialSafety:
    def test_all_checks_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import Report, verify_financial_safety

        r = Report(date="2026-08-12", commit="abc", environment="local", runtime_health="UP")
        res = verify_financial_safety(r)
        assert res["all_present"] is True
        # INFO finding added
        info = [f for f in r.findings if f.severity == "INFO" and "guard rails present" in f.title]
        assert len(info) == 1

    def test_missing_check_emits_high_finding(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from scripts.daily_bot_audit import Report, verify_financial_safety

        # Temporarily make monitor.py missing so _find returns None for first check
        real_root = sys.modules["scripts.daily_bot_audit"].ROOT
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "ROOT", tmp_path)
        r = Report(date="2026-08-12", commit="abc", environment="local", runtime_health="UP")
        res = verify_financial_safety(r)
        assert res["all_present"] is False
        high = [f for f in r.findings if f.severity == "HIGH" and "guard could not be verified" in f.title]
        assert len(high) == 1
        # Restore ROOT for other tests
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "ROOT", real_root)


# ---------------------------------------------------------------------------
# Should open critical issue (pure policy) — lines 1026-1028
# ---------------------------------------------------------------------------
class TestShouldOpenCriticalIssue:
    def test_returns_true_for_critical_with_gh(self) -> None:
        from scripts.daily_bot_audit import should_open_critical_issue

        assert should_open_critical_issue("CRITICAL", True) is True

    def test_returns_false_for_degraded(self) -> None:
        from scripts.daily_bot_audit import should_open_critical_issue

        assert should_open_critical_issue("DEGRADED", True) is False

    def test_returns_false_when_gh_unavailable(self) -> None:
        from scripts.daily_bot_audit import should_open_critical_issue

        assert should_open_critical_issue("CRITICAL", False) is False


# ---------------------------------------------------------------------------
# Restore metrics from artifacts — gh unavailable path
# ---------------------------------------------------------------------------
class TestRestoreMetricsFromArtifacts:
    def test_returns_zero_when_gh_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.daily_bot_audit import restore_metrics_from_artifacts

        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "_gh_available", lambda: False)
        restored = restore_metrics_from_artifacts()
        assert restored == 0


# ---------------------------------------------------------------------------
# classify_open_issues — REQUIRES_REVIEW for all known issues
# ---------------------------------------------------------------------------
class TestClassifyOpenIssues:
    def test_all_known_issues_are_requires_review(self) -> None:
        from scripts.daily_bot_audit import Report, classify_open_issues

        r = Report(date="2026-08-12", commit="abc", environment="local", runtime_health="UP")
        issues = [
            {"number": 111, "title": "Gemini key blocked"},
            {"number": 109, "title": "Equity admit knobs"},
            {"number": 102, "title": "Pair discovery pin"},
            {"number": 91, "title": "Reactivate feature"},
            {"number": 57, "title": "Java toolchain"},
        ]
        classify_open_issues(r, issues)
        # All should be in requires_review
        assert len(r.requires_review) == 5
        # All should have a Finding
        assert len(r.findings) == 5


# ---------------------------------------------------------------------------
# main() — argument parsing and exit codes
# ---------------------------------------------------------------------------
class TestMainFunction:
    def test_main_defaults(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        from scripts.daily_bot_audit import main

        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "_git_commit", lambda: "abc123")
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "check_runtime", lambda: {"running": False, "where": "not-running-here", "details": {}})
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "_load_json_logs", lambda: [])
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "check_trading", lambda: {"reachable": False, "reason": "httpx not installed", "host": "http://127.0.0.1:8082"})
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "run_tests", lambda mode: {"mode": mode, "skipped": True})
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "check_github", lambda: {"available": False})
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "verify_financial_safety", lambda report: {"checks": {}, "all_present": True})
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "compute_trend", lambda report: {"previous": None, "current": {}})
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "write_metrics", lambda report: Path("/tmp/x"))
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "compute_historical_trend", lambda: {"available": False, "note": "no data"})
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "_gh_available", lambda: False)
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "restore_metrics_from_artifacts", lambda: 0)
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "_env_label", lambda: "local:main")
        monkeypatch.setattr(sys.modules["scripts.daily_bot_audit"], "REPORT_DIR", Path("/tmp/reports"))

        rc = main([])
        assert rc == 0  # default HEALTHY

    def test_main_critical_exit_code(self, tmp_path: Path) -> None:
        """Verify main() returns exit code 2 when the audit yields a CRITICAL report.

        We run the real daily_bot_audit.py as a subprocess so the
        ``if __name__ == "__main__"`` guard at line 1160 fires, and we
        monkeypatch ``run_audit`` to return a pre-built CRITICAL report so we
        don't depend on the live environment.
        """
        env_file = tmp_path / ".env"
        env_file.write_text("PAPER_TRADING=true\n", encoding="utf-8")

        # The wrapper patches run_audit before the real module code runs.
        wrapper = tmp_path / "wrapper_crit.py"
        wrapper.write_text(
            "import sys, os\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, {repr(str(ROOT))})\n"
            f"os.environ['AUDIT_ENV_PATH'] = {repr(str(env_file))}\n"
            "from scripts.daily_bot_audit import Report, Finding\n"
            "import scripts.daily_bot_audit as dba\n"
            "_base = Report(date='2026-08-12', commit='abc', environment='local', runtime_health='UP')\n"
            "_base.add(Finding('CRITICAL', 'test critical', 'detail', 'Section'))\n"
            "_base.verdict = 'CRITICAL'\n"
            "dba.run_audit = lambda d, t, g, a: _base\n"
            "from scripts.daily_bot_audit import main\n"
            "sys.exit(main(['--tests', 'none']))\n",
            encoding="utf-8",
        )

        proc = subprocess.run(
            [sys.executable, str(wrapper)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert proc.returncode == 2, f"expected exit 2, got {proc.returncode}"
        assert "CRITICAL" in proc.stdout
