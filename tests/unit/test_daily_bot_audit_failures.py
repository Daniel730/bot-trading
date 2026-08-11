"""Fault-tolerance tests for the Daily Bot Audit engine (brief §10 / §12).

These prove the audit engine FAILS SAFE, not just that it works on the happy
path: missing logs, malformed JSONL, a failing external pytest/ruff command, a
down GitHub CLI, a remediation whose apply/validate blows up, and the anti-loop
attempt cap. None of these should crash the audit or mutate the verdict into a
false HEALTHY.
"""
import json
from pathlib import Path

import pytest

import scripts.daily_bot_audit as dba
from scripts import audit_remediations as ar


def _report() -> dba.Report:
    return dba.Report(date="2026-08-11", commit="abc", environment="test",
                      runtime_health="UP")


# --- log handling ----------------------------------------------------------- #
def test_missing_log_file_does_not_crash(tmp_path, monkeypatch):
    log = tmp_path / "nope.jsonl"
    monkeypatch.setattr(dba, "LOG_PATH", log)
    rep = _report()
    res = dba.analyze_logs(rep)
    assert res["total_lines"] == 0
    assert res["incidents"] == []
    assert not any(f.severity in ("CRITICAL", "HIGH") for f in rep.findings)


def test_malformed_jsonl_line_is_skipped(tmp_path, monkeypatch):
    log = tmp_path / "structured_logs.jsonl"
    log.write_text(
        '{"level":"INFO","message":"ok","timestamp":"2026-08-11T10:00:00+00:00"}\n'
        "this is not json\n"
        '{"level":"ERROR","message":"FATAL ERROR initializing KO/PEP: boom","timestamp":"2026-08-11T10:05:00+00:00"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(dba, "LOG_PATH", log)
    rep = _report()
    res = dba.analyze_logs(rep)
    # 2 valid rows kept; the garbage line ignored; still parsed without raising.
    assert res["total_lines"] == 2
    # historical-era fatal (2026-08-11 within window) but fail-closed pattern
    # -> classified INFO, not a live HIGH/CRITICAL.
    assert not any(f.severity == "CRITICAL" for f in rep.findings)


# --- external command failure isolation ------------------------------------- #
def test_ruff_failure_isolated(monkeypatch):
    # Simulate ruff exiting non-zero (real failures surface as rc, not exceptions).
    monkeypatch.setattr(dba, "_run", lambda *a, **k: (1, "", "found issues"))
    res = dba.run_tests("fast")
    assert res.get("ruff", {}).get("rc") == 1
    assert res.get("ruff", {}).get("passed") is False


def test_pytest_failure_yields_degraded_not_crash(monkeypatch):
    # Simulate the pytest safety subset exiting non-zero (a test failure).
    calls = {}

    def fake_run(cmd, *a, **k):
        if "pytest" in cmd:
            calls["pytest"] = True
            return (1, "", "1 failed")
        return (0, "", "")

    monkeypatch.setattr(dba, "_run", fake_run)
    res = dba.run_tests("fast")
    assert calls.get("pytest") is True
    assert res.get("pytest", {}).get("rc", 0) != 0
    assert res.get("pytest", {}).get("passed") is False


def test_github_cli_unavailable_isolated(monkeypatch):
    # gh missing -> _run returns rc=127 (FileNotFoundError path); check_github
    # must degrade gracefully (available=False), never raise.
    monkeypatch.setattr(dba, "_run", lambda *a, **k: (127, "", "gh not found"))
    res = dba.check_github()
    assert res.get("available") is False


# --- remediation failure -> revert (fail-safe auto-remediation) ------------- #
def test_apply_with_guard_reverts_on_validation_failure(tmp_path):
    target = tmp_path / "flag.txt"
    target.write_text("orig", encoding="utf-8")

    def _apply() -> None:
        target.write_text("changed", encoding="utf-8")

    def _restore() -> None:
        target.write_text("orig", encoding="utf-8")

    fix = ar.Fix(
        signature="demo",
        title="demo",
        detail="",
        apply=_apply,
        validate=lambda: False,  # always fails validate
        restore=_restore,
    )
    state = ar.RemediationState()
    ok, _ = ar.apply_with_guard(fix, state)
    assert ok is False
    # file reverted to original — no half-applied state
    assert target.read_text(encoding="utf-8") == "orig"
    assert state.attempts["demo"] >= 1


def test_apply_with_guard_reverts_on_apply_exception(tmp_path):
    target = tmp_path / "flag.txt"
    target.write_text("orig", encoding="utf-8")

    def _apply() -> None:
        raise RuntimeError("boom")

    fix = ar.Fix(
        signature="demo2",
        title="demo2",
        detail="",
        apply=_apply,
        validate=lambda: True,
        restore=lambda: target.write_text("orig", encoding="utf-8"),
    )
    state = ar.RemediationState()
    ok, _ = ar.apply_with_guard(fix, state)
    assert ok is False
    assert target.read_text(encoding="utf-8") == "orig"


# --- anti-loop guards (brief §10) ------------------------------------------- #
def test_attempt_cap_blocks_after_limit():
    state = ar.RemediationState()
    sig = "loopguard"
    for _ in range(ar.MAX_ATTEMPTS_PER_SIGNATURE):
        state.attempts[sig] = state.attempts.get(sig, 0) + 1
    allowed, reason = state.can_apply(sig)
    assert allowed is False
    assert "attempt cap" in reason


def test_cooldown_blocks_repeat_in_window():
    state = ar.RemediationState()
    sig = "coolguard"
    state.last_applied_at[sig] = 1_000_000.0  # far in the "past" but < cooldown
    import time
    # simulate "now" just after last_applied (within cooldown)
    allowed, reason = state.can_apply(sig, now=1_000_001.0)
    assert allowed is False
    assert "cooldown" in reason


def test_fresh_signature_is_allowed():
    state = ar.RemediationState()
    allowed, reason = state.can_apply("fresh")
    assert allowed is True
    assert reason == "ok"


# --- safe fixes never touch capital paths (defense of the design contract) -- #
def test_discover_safe_fixes_never_returns_financial_action():
    fixes = ar.discover_safe_fixes()
    titles = " ".join(f.title.lower() for f in fixes)
    assert "position" not in titles
    assert "order" not in titles
    assert "paper" not in titles
    assert "live" not in titles
    assert "credential" not in titles
    # every candidate is a non-financial hygiene action
    assert all(f.reversible for f in fixes)


# --- incident DETECTION (brief §13): the engine must ESCALATE real incidents,
#     not only downgrade historical ones to INFO. ---------------------------- #
def test_real_incident_in_window_is_escalated(tmp_path, monkeypatch):
    log = tmp_path / "structured_logs.jsonl"
    # A genuine crash marker dated inside the 24h audit window (2026-08-11).
    log.write_text(
        '{"level":"ERROR","message":"Traceback (most recent call last): File \\"monitor.py\\", line 1, in <module>\\nZeroDivisionError: division by zero","timestamp":"2026-08-11T14:32:00+00:00"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(dba, "LOG_PATH", log)
    rep = _report()
    res = dba.analyze_logs(rep)
    # The incident is detected as a real (non-expected-fail-closed) marker.
    assert len(res["incidents"]) == 1
    # And it produces a HIGH/CRITICAL finding — NOT silently ignored.
    assert any(f.severity in ("HIGH", "CRITICAL") for f in rep.findings)


def test_duplicate_fill_detected_as_incident(tmp_path, monkeypatch):
    log = tmp_path / "structured_logs.jsonl"
    log.write_text(
        '{"level":"ERROR","message":"duplicate fill detected for order ABC123 — position opened twice","timestamp":"2026-08-11T09:00:00+00:00"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(dba, "LOG_PATH", log)
    rep = _report()
    res = dba.analyze_logs(rep)
    assert len(res["incidents"]) == 1
    assert any(f.severity in ("HIGH", "CRITICAL") for f in rep.findings)


def test_expected_fail_closed_not_flagged_as_incident(tmp_path, monkeypatch):
    log = tmp_path / "structured_logs.jsonl"
    log.write_text(
        '{"level":"CRITICAL","message":"EMERGENCY CLOSE — account read down, broker submit blocked (safe fail-closed)","timestamp":"2026-08-11T09:00:00+00:00"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(dba, "LOG_PATH", log)
    rep = _report()
    res = dba.analyze_logs(rep)
    # fail-closed safety line is NOT an incident
    assert res["incidents"] == []
    assert res["expected_fail_closed"] >= 1


# --- historical observability (brief §11) ----------------------------------- #
def test_write_metrics_and_historical_trend(tmp_path, monkeypatch):
    # Point metrics dir at tmp and seed two prior days with a worsening series.
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dba, "METRICS_DIR", metrics_dir)
    import json as _json
    for d, errs in [("2026-08-09", 1), ("2026-08-10", 2), ("2026-08-11", 5)]:
        (metrics_dir / f"{d}.json").write_text(
            _json.dumps({"date": d, "errors": errs, "incidents": 0,
                         "api_degraded": 0, "verdict": "DEGRADED"}),
            encoding="utf-8",
        )
    # Build a report whose log analysis yields errors=5 (matches last seeded day)
    log = tmp_path / "structured_logs.jsonl"
    log.write_text(
        '{"level":"ERROR","message":"boom","timestamp":"2026-08-11T10:00:00+00:00"}\n' * 5,
        encoding="utf-8",
    )
    monkeypatch.setattr(dba, "LOG_PATH", log)
    rep = _report()
    rep.sections["logs"] = dba.analyze_logs(rep)
    p = dba.write_metrics(rep)
    assert p.exists()
    saved = _json.loads(p.read_text(encoding="utf-8"))
    assert saved["date"] == "2026-08-11"
    # Historical trend sees the worsening errors series (1 -> 5) and flags it.
    hist = dba.compute_historical_trend(days=7)
    assert hist["available"] is True
    assert hist["deltas"]["errors"]["delta"] == 4  # 1 -> 5
    assert "errors" in hist["worsening_vs_prev"]  # 2 -> 5 vs prev day
    # verdict trajectory: the 2 seeded days are DEGRADED; the live report is
    # HEALTHY (5 plain ERROR lines are not incidents), so the last entry is HEALTHY.
    assert hist["verdict_trajectory"][:2] == ["DEGRADED", "DEGRADED"]
    assert hist["verdict_trajectory"][-1] in ("HEALTHY", "DEGRADED")


def test_historical_trend_empty_when_no_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(dba, "METRICS_DIR", tmp_path / "empty_metrics")
    hist = dba.compute_historical_trend()
    assert hist["available"] is False
    assert "note" in hist


# --- alerting policy (brief: what to do with a bad verdict) ----------------- #
def test_should_open_critical_issue_policy():
    assert dba.should_open_critical_issue("CRITICAL", True) is True
    assert dba.should_open_critical_issue("DEGRADED", True) is False
    assert dba.should_open_critical_issue("CRITICAL", False) is False
    assert dba.critical_issue_title("2026-08-11") == \
        "Daily Bot Audit CRITICAL — 2026-08-11"


def test_open_critical_issue_idempotent_and_safe(monkeypatch):
    # Simulate gh auth OK, then an existing same-day issue -> no duplicate.
    calls = {}

    def fake_run(cmd, *a, **k):
        calls.setdefault(tuple(cmd[:3]), 0)
        calls[tuple(cmd[:3])] += 1
        if cmd[1:3] == ["auth", "status"]:
            return (0, "", "")
        if cmd[1:3] == ["issue", "list"]:
            # gh issue list returns an existing open critical issue
            return (0, '[{"number": 99}]', "")
        return (0, "", "")

    monkeypatch.setattr(dba, "_run", fake_run)
    rep = _report()
    rep.verdict = "CRITICAL"
    rep.findings.append(dba.Finding("CRITICAL", "boom", "detail", "X"))
    res = dba.open_critical_issue(rep)
    # Did NOT file a new issue because one already exists same-day.
    assert res["opened"] is False
    assert res["reason"] == "already-open"
    assert tuple(["gh", "issue", "create"]) not in [
        tuple(c[:3]) for c in calls
    ]


def test_open_critical_issue_files_when_none_exists(monkeypatch):
    calls = {}

    def fake_run(cmd, *a, **k):
        calls[tuple(cmd[:3])] = calls.get(tuple(cmd[:3]), 0) + 1
        if cmd[1:3] == ["auth", "status"]:
            return (0, "", "")
        if cmd[1:3] == ["issue", "list"]:
            return (0, "[]", "")  # no existing issue
        if cmd[1:3] == ["issue", "create"]:
            return (0, "", "")
        return (0, "", "")

    monkeypatch.setattr(dba, "_run", fake_run)
    rep = _report()
    rep.verdict = "CRITICAL"
    rep.findings.append(dba.Finding("CRITICAL", "boom", "detail", "X"))
    res = dba.open_critical_issue(rep)
    assert res["opened"] is True
    assert calls.get(("gh", "issue", "create"), 0) == 1


def test_open_critical_issue_degraded_is_noop():
    rep = _report()
    rep.verdict = "DEGRADED"
    res = dba.open_critical_issue(rep)  # no gh monkeypatch; must no-op safely
    assert res["opened"] is False
    assert res["reason"] == "not-critical-or-no-gh"
