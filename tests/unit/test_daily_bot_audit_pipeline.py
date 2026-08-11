"""End-to-end integration tests for the Daily Bot Audit pipeline.

These go beyond unit/component tests (analyse_logs alone) and exercise the
full run_audit() path with injected incidents + the main() dispatch path for
--issue-on-critical and --autofix, with gh/external commands mocked. No
network, fully deterministic.
"""
from pathlib import Path
from unittest import mock

import pytest

import scripts.daily_bot_audit as dba


def _critical_log(tmp_path):
    """6 real Traceback incidents -> CRITICAL verdict."""
    log = tmp_path / "structured_logs.jsonl"
    lines = '\n'.join(
        '{"level":"ERROR","message":"Traceback (most recent call last): boom","timestamp":"2026-08-11T10:0%d:00+00:00"}\n'
        % i for i in range(6)
    )
    log.write_text(lines, encoding="utf-8")
    return log


def _degraded_log(tmp_path):
    """Single real Traceback incident -> HIGH finding -> DEGRADED verdict."""
    log = tmp_path / "structured_logs.jsonl"
    log.write_text(
        '{"level":"ERROR","message":"Traceback (most recent call last): File \\"monitor.py\\", in <module>\\nZeroDivisionError: integer division by zero","timestamp":"2026-08-11T14:32:00+00:00"}\n',
        encoding="utf-8",
    )
    return log


def _paper_env(tmp_path):
    p = tmp_path / ".env"
    p.write_text(
        "PAPER_TRADING=true\n"
        "LIVE_CAPITAL_DANGER=false\n"
        "BROKERAGE_PROVIDER=ALPACA\n"
        "ALPACA_API_KEY=your_alpaca_key_REPLACE_ME\n"
        "ALPACA_API_SECRET=your_alpaca_secret_REPLACE_ME\n"
        "MONITOR_ENTRY_ZSCORE=2.0\n",
        encoding="utf-8",
    )
    return p


# --- run_audit end-to-end: incident -> verdict --- #
def test_run_audit_degraded_with_real_incident(tmp_path, monkeypatch):
    """Single real incident (Traceback) -> HIGH finding -> DEGRADED verdict.
    (CRITICAL requires 6+ real incidents or a missing financial guard.)"""
    log = _degraded_log(tmp_path)
    monkeypatch.setattr(dba, "LOG_PATH", log)
    rep = dba.run_audit("2026-08-11", "none", no_github=True, no_autofix=True)
    assert rep.verdict == "DEGRADED"
    assert any(f.severity == "HIGH" for f in rep.findings)
    assert any("Traceback" in f.detail for f in rep.findings)
    assert rep.sections["logs"]["incidents"]


def test_run_audit_critical_with_many_incidents(tmp_path, monkeypatch):
    """6+ real incidents -> CRITICAL verdict (one CRITICAL finding in Logs section)."""
    log = _critical_log(tmp_path)
    monkeypatch.setattr(dba, "LOG_PATH", log)
    rep = dba.run_audit("2026-08-11", "none", no_github=True, no_autofix=True)
    assert rep.verdict == "CRITICAL"
    assert any(f.severity == "CRITICAL" and f.section == "Logs" for f in rep.findings)


def test_run_audit_clean_log_is_healthy(tmp_path, monkeypatch):
    log = tmp_path / "structured_logs.jsonl"
    log.write_text(
        '{"level":"INFO","message":"iteration complete","timestamp":"2026-08-11T10:00:00+00:00"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(dba, "LOG_PATH", log)
    rep = dba.run_audit("2026-08-11", "none", no_github=True, no_autofix=True)
    assert rep.verdict == "HEALTHY"
    # run_audit always emits at least one INFO finding (financial-safety guard
    # rails present), so HEALTHY means no HIGH/CRITICAL/MEDIUM findings.
    assert not any(f.severity in ("HIGH", "CRITICAL", "MEDIUM") for f in rep.findings)


# --- main() dispatch: --issue-on-critical + --autofix --- #
def test_main_issue_on_critical_opens_issue_when_critical(monkeypatch, tmp_path):
    """CRITICAL verdict (6+ real incidents) with --issue-on-critical opens the issue."""
    log = _critical_log(tmp_path)
    monkeypatch.setattr(dba, "LOG_PATH", log)
    called = {}

    def fake_run(cmd, *a, **k):
        if cmd[0] == "gh":
            called["gh"] = called.get("gh", []) + [cmd[1:]]
        else:
            called.setdefault("other", []).append(cmd[0])
        return (0, "", "")

    monkeypatch.setattr(dba, "_run", fake_run)
    # Simulate CI so the issue-open policy (should_open_critical_issue) passes.
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    with mock.patch.object(dba, "print"):
        rc = dba.main(["--tests", "none", "--issue-on-critical"])

    assert rc == 2  # CRITICAL
    # gh issue list (idempotency check) was called
    assert any(c[:2] == ["issue", "list"] for c in called.get("gh", []))
    # gh issue create was called (critical issue dispatch)
    assert any(c[:2] == ["issue", "create"] for c in called.get("gh", []))


def test_main_without_issue_flag_does_not_open_issue(monkeypatch, tmp_path):
    """CRITICAL verdict (6+ real incidents), without --issue-on-critical, never
    calls gh issue create — the orchestration gate is the CLI flag."""
    log = _critical_log(tmp_path)
    monkeypatch.setattr(dba, "LOG_PATH", log)

    called = {}

    def fake_run(cmd, *a, **k):
        if cmd[0] == "gh":
            called["gh"] = called.get("gh", []) + [cmd[1:]]
        return (0, "", "")

    monkeypatch.setattr(dba, "_run", fake_run)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    with mock.patch.object(dba, "print"):
        rc = dba.main(["--tests", "none"])  # no --issue-on-critical

    assert rc == 2  # CRITICAL verdict (6 incidents)
    assert not any(c[:2] == ["issue", "create"] for c in called.get("gh", []))


def test_main_autofix_hygiene_only(monkeypatch, tmp_path):
    # --autofix must run safe hygiene and never produce a capital-affecting fix.
    log = tmp_path / "structured_logs.jsonl"
    log.write_text(
        '{"level":"INFO","message":"iteration complete","timestamp":"2026-08-11T10:00:00+00:00"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(dba, "LOG_PATH", log)
    env = _paper_env(tmp_path)
    monkeypatch.setenv("APP_ENV_FILE", str(env))

    called = {}

    def fake_run(cmd, *a, **k):
        called["cmd"] = called.get("cmd", []) + [cmd]
        return (0, "", "")

    monkeypatch.setattr(dba, "_run", fake_run)

    with mock.patch.object(dba, "print"):
        rc = dba.main(["--tests", "none", "--autofix"])

    assert rc == 0  # HEALTHY
    # No trading ops: not placing/cancelling orders, not touching capital.
    for cmd in called.get("cmd", []):
        joined = " ".join(str(c) for c in cmd)
        assert "order" not in joined.lower() or "cancel" not in joined.lower()
        assert "paper_trade" not in joined
        assert "live_capital" not in joined
