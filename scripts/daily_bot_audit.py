#!/usr/bin/env python3
"""Daily Bot Audit — continuous, evidence-based maintenance for bot-trading.

This is the orchestrator described in docs/DAILY_AUDIT.md. It is designed to be:

* REPRODUCIBLE  — pure Python stdlib + the repo's own tools (ruff, bug_hunt,
                  pytest). No new infra required to run locally.
* VERSIONED     — lives in the repo under scripts/ and is exercised by CI.
* OBSERVABLE   — writes reports/daily-audit/YYYY-MM-DD.md + a latest.md pointer
                  and prints a concise verdict.
* IDEMPOTENT    — re-running produces the same findings; the report is
                  date-stamped and the latest pointer is just a copy.
* SAFE          — it NEVER places/cancels orders, never flips trading mode,
                  never touches credentials/endpoints/sizing. Financial-safety
                  gaps are emitted as REQUIRES_REVIEW, never auto-fixed.

Sections (mapped to the maintenance brief):
  Runtime       — process/container up, restarts, OOM, CPU/RAM/disk, uptime.
  Logs          — structured-log pattern analysis (expected fail-closed vs real
                  incidents), trend vs previous report.
  Trading       — positions/orders/PnL/exposure via dashboard API if reachable.
  Software      — pytest safety subset, ruff, bug_hunt_audit (CI-mirroring).
  GitHub        — new/critical issues, failed CI, PRs, dependabot.
  FinancialSafety — static verification of the BUG->TRADE->LOSS guards (ADR-003,
                    006, 008, 010, 012) with file:line evidence.
  AutomaticFixes / RequiresReview / Trend / Verdict.

Usage:
  python scripts/daily_bot_audit.py [--date YYYY-MM-DD] [--tests fast|full|none]
                                    [--no-github] [--no-autofix]

Exit code: 0 healthy, 1 degraded, 2 critical (useful for cron/CI gating).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "daily-audit"
LATEST_REPORT = REPORT_DIR / "latest.md"
# Paths are overridable so the audit works both locally (repo-mirrored logs)
# and on bot-server (where the bot actually runs, logs/env live elsewhere).
LOG_PATH = Path(os.environ.get("AUDIT_LOG_PATH", ROOT / "logs" / "structured_logs.jsonl"))
# On bot-server the real env is /home/daniel/.env.trading (APP_ENV_FILE); locally
# it's the repo .env. Never require a secrets file to exist.
_ENV_DEFAULT = os.environ.get("APP_ENV_FILE") or (ROOT / ".env")
ENV_PATH = Path(os.environ.get("AUDIT_ENV_PATH", _ENV_DEFAULT))
ENV_TEMPLATE = ROOT / ".env.template"
GIT = ROOT
# The dashboard API port differs per deployment (8082 on bot-server, 8080 locally).
BOT_API_HOST = os.environ.get("AUDIT_BOT_HOST", "http://127.0.0.1:8082")

SEV_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
# Verdict precedence: CRITICAL>HIGH>...  (used to pick overall verdict)
SEV_TO_VERDICT = {"CRITICAL": "CRITICAL", "HIGH": "DEGRADED", "MEDIUM": "DEGRADED"}


# --------------------------------------------------------------------------- #
# Finding model
# --------------------------------------------------------------------------- #
@dataclass
class Finding:
    severity: str
    title: str
    detail: str
    section: str
    evidence: str = ""
    requires_review: bool = False

    def to_md(self) -> str:
        tag = " [REQUIRES_REVIEW]" if self.requires_review else ""
        body = f"- **[{self.severity}]{tag}** {self.title}"
        if self.detail:
            body += f": {self.detail}"
        if self.evidence:
            body += f"\n  - evidence: `{self.evidence}`"
        return body


@dataclass
class Report:
    date: str
    commit: str
    environment: str
    runtime_health: str
    findings: list[Finding] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)
    fixes_applied: list[str] = field(default_factory=list)
    requires_review: list[str] = field(default_factory=list)
    trend: dict[str, Any] = field(default_factory=dict)
    verdict: str = "HEALTHY"

    def add(self, f: Finding) -> None:
        self.findings.append(f)

    def highest_severity(self) -> Optional[str]:
        for sev in SEV_ORDER:
            if any(f.severity == sev for f in self.findings):
                return sev
        return None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], timeout: int = 120, cwd: Path = ROOT) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except FileNotFoundError as exc:
        return 127, "", str(exc)


def _git_commit() -> str:
    rc, out, _ = _run(["git", "-C", str(GIT), "rev-parse", "--short", "HEAD"])
    return out.strip() or "unknown"


def _load_json_logs() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    rows: list[dict] = []
    for line in LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


# --------------------------------------------------------------------------- #
# Section: Runtime
# --------------------------------------------------------------------------- #
def check_runtime() -> dict:
    """Detect whether the bot is actually running in THIS environment.

    The audit host (dev machine / CI runner) usually is NOT the bot-server, so
    we report honestly instead of pretending the bot is down. Real runtime
    checks run on bot-server via the existing infra/ops_* scripts.
    """
    out: dict = {"running": False, "where": "this-audit-host", "details": {}}
    # Docker present?
    rc, _, _ = _run(["docker", "info"], timeout=10)
    docker_ok = rc == 0
    # monitor process?
    rc, pg, _ = _run(["pgrep", "-af", "monitor.py"], timeout=10)
    monitor_proc = bool(pg.strip()) if rc == 0 else False
    if docker_ok:
        rc, dout, _ = _run(
            ["docker", "ps", "-a", "--filter", "name=trading-bot-bot-1",
             "--format", "{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}"],
            timeout=15,
        )
        if dout.strip():
            status, rc_count, oom = (dout.strip().split("|") + ["", "", ""])[:3]
            out["running"] = status == "running"
            out["details"] = {"docker_status": status, "restart_count": rc_count, "oom_killed": oom}
            out["where"] = "docker(bot-server profile)"
    elif monitor_proc:
        out["running"] = True
        out["where"] = "local-process"
    else:
        out["running"] = False
        out["where"] = "not-running-here"
    return out


# --------------------------------------------------------------------------- #
# Section: Log analysis (pattern rules, not naive ERROR counting)
# --------------------------------------------------------------------------- #
# Expected fail-closed safety lines (these are CORRECT operation, not incidents).
_EXPECTED_FAIL_CLOSED = re.compile(
    r"(NEEDS_MANUAL_RECONCILIATION|PARTIAL_EXPOSURE|ATOMIC FAILURE|EMERGENCY CLOSE|"
    r"EXACTLY-ONCE|pending read down|account read down|broker submit blocked|"
    r"capital_halt|Leg B NOT placed|execution blocked|requires manual reconciliation|"
    r"CRITICAL - EMERGENCY CLOSE UNKNOWN|CRITICAL - EMERGENCY CLOSE UNCONFIRMED|"
    r"Close order .* Manual|Ledger NOT closed)",
    re.I,
)
# Real incidents: crashes, OOM, restart loops, duplicate fills, unknown exposure.
_INCIDENT = re.compile(
    r"(Traceback \(|OutOfMemory|OOM killed|Segmentation|unhandled exception|uncaught|"
    r"duplicate (fill|order)|unknown exposure|double (fill|open)|restart loop|"
    r"FATAL ERROR|RecursionError|MemoryError|BrokenPipe)",
    re.I,
)
# API/network degradation (not necessarily an incident by itself).
_API_DEGRADED = re.compile(
    r"(Failed to fetch|timeout|timed out|rate.?limit|429|503|connection reset|"
    r"unauthorized|API_KEY_SERVICE_BLOCKED|rejected|VETO|BLOCK)",
    re.I,
)


def analyze_logs(report: Report, since_iso: Optional[str] = None) -> dict:
    rows = _load_json_logs()
    by_level: dict[str, int] = {}
    expected = 0
    incidents: list[dict] = []
    api_deg = 0
    window: list[dict] = []
    # Window = the 24h ending at the audit date (report.date), default. This is
    # robust whether the newest log row is today or days old: anything older
    # than the audit day - 24h is treated as historical (not an active incident).
    try:
        audit_dt = datetime.fromisoformat(report.date + "T00:00:00+00:00")
        cutoff = audit_dt.timestamp() - 24 * 3600
    except ValueError:
        cutoff = None
    for r in rows:
        lvl = str(r.get("level") or "").upper()
        by_level[lvl] = by_level.get(lvl, 0) + 1
        msg = r.get("message", "") or ""
        ts = r.get("timestamp", "")
        in_window = True
        if cutoff:
            try:
                in_window = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() >= cutoff
            except ValueError:
                in_window = False
        if not in_window:
            continue
        window.append(r)
        if _EXPECTED_FAIL_CLOSED.search(msg):
            expected += 1
            continue
        if _INCIDENT.search(msg):
            incidents.append({"ts": ts, "level": lvl, "msg": msg[:200]})
        if _API_DEGRADED.search(msg):
            api_deg += 1
    res = {
        "total_lines": len(rows),
        "window_lines": len(window),
        "levels": by_level,
        "expected_fail_closed": expected,
        "api_degraded_hits": api_deg,
        "incidents": incidents[:20],
    }
    # Findings
    if incidents:
        sev = "HIGH" if len(incidents) <= 5 else "CRITICAL"
        report.add(
            Finding(
                sev, "Real incident patterns in logs",
                f"{len(incidents)} crash/OOM/duplicate/unknown-exposure markers in window",
                "Logs", evidence="; ".join(i["msg"][:80] for i in incidents[:3]),
                requires_review=True,
            )
        )
    # Distinguish same-day recurrence from older-but-in-window markers.
    sameday = [i for i in incidents if i["ts"][:10] == report.date]
    if incidents and not sameday:
        report.add(
            Finding(
                "INFO", "Historical incident markers (no same-day recurrence)",
                f"{len(incidents)} incident markers fall in the 24h window but none are dated {report.date}; "
                "review if they recur on the current day",
                "Logs", evidence=f"oldest={incidents[-1]['ts']}",
            )
        )
    # Stale structured log file (not rotated)
    if LOG_PATH.exists():
        age_days = (time.time() - LOG_PATH.stat().st_mtime) / 86400
        if age_days > 7:
            report.add(
                Finding(
                    "LOW", "Structured log file not rotated recently",
                    f"{LOG_PATH.name} is {age_days:.1f}d old (log rotation may be inactive)",
                    "Logs", evidence=str(LOG_PATH),
                )
            )
    return res


# --------------------------------------------------------------------------- #
# Section: Trading (best-effort via dashboard API)
# --------------------------------------------------------------------------- #
def check_trading() -> dict:
    try:
        import httpx
    except ImportError:
        return {"reachable": False, "reason": "httpx not installed in this env", "host": BOT_API_HOST}
    try:
        with httpx.Client(base_url=BOT_API_HOST, timeout=8.0) as c:
            r = c.get("/api/system/health")
            if r.is_success:
                return {"reachable": True, "health": r.json(), "host": BOT_API_HOST}
    except Exception as exc:  # noqa: BLE001
        return {"reachable": False, "reason": f"{type(exc).__name__}: {exc}", "host": BOT_API_HOST}
    return {"reachable": False, "reason": "health endpoint not success", "host": BOT_API_HOST}


# --------------------------------------------------------------------------- #
# Section: Software tests (CI-mirroring)
# --------------------------------------------------------------------------- #
# Fast safety gate = bug_hunt + ruff + the broker/config safety contract tests
# that are quick to import. The heavy monitor_execution/closing tests are part of
# --tests full (run in CI with a 15-min timeout).
FAST_TEST_TARGETS = [
    "tests/unit/test_alpaca_provider.py",
    "tests/unit/test_config_broker_routes.py",
    "tests/unit/test_production_soak_gate.py",
    "tests/unit/test_runtime_alert_rules.py",
    "tests/unit/test_dashboard_wallet_sync.py",
    "tests/unit/test_startup_unresolved_execution_state.py",
    "tests/unit/test_compose_restart_lifecycle.py",
    "tests/unit/test_backend_compose_secrets.py",
]
FULL_TEST_TARGETS = [
    "tests/unit/test_monitor_execution.py",
    "tests/unit/test_monitor_closing.py",
]
# Modules that cannot be collected on this Windows venv (optional Linux-only
# deps: grpc, edgar). Reported honestly as ENVIRONMENT, never as code failures.
KNOWN_UNCOLLECTABLE = [
    "tests/benchmark/test_idempotency_load.py",
    "tests/benchmark/test_value_traps.py",
    "tests/integration/test_cik_ground_truth.py",
    "tests/integration/test_kill_switch_liquidation.py",
    "tests/integration/test_latency_audit.py",
    "tests/integration/test_risk_volatility_switch.py",
    "tests/integration/test_telemetry_latency.py",
    "tests/unit/test_execution_idempotency_state_machine.py",
    "tests/unit/test_fundamental_analyst.py",
    "tests/unit/test_sec_data.py",
]


def run_tests(mode: str) -> dict:
    res: dict = {"mode": mode}
    if mode == "none":
        return {**res, "skipped": True}

    # 1) bug_hunt_audit (fast deploy-readiness / secret-hygiene preflight)
    rc, out, err = _run(
        [sys.executable, "scripts/bug_hunt_audit.py"],
        timeout=120,
    )
    res["bug_hunt"] = {"rc": rc, "passed": rc == 0, "output": (out or err)[-400:]}

    # 2) ruff (undefined names / syntax) — mirrors CI
    rc, out, err = _run(
        [sys.executable, "-m", "ruff", "check", "src", "scripts", "tests"],
        timeout=180,
    )
    res["ruff"] = {"rc": rc, "passed": rc == 0, "output": (out or err)[-400:]}

    # 3) pytest safety subset (plus full monitor tests in --tests full)
    targets = list(FAST_TEST_TARGETS)
    if mode == "full":
        targets += FULL_TEST_TARGETS
    if not targets:
        res["pytest"] = {"skipped": True}
        return res
    ignore = [f"--ignore={m}" for m in KNOWN_UNCOLLECTABLE]
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
           "--asyncio-mode=auto", *ignore, *targets]
    rc, out, err = _run(cmd, timeout=540)
    # Parse summary line like "123 passed, 2 failed in 12.34s"
    summary = ""
    for line in (out + err).splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            summary = line.strip()
    res["pytest"] = {
        "rc": rc,
        "passed": rc == 0,
        "summary": summary[-300:],
        "uncollectable_reported": KNOWN_UNCOLLECTABLE,
    }
    return res


# --------------------------------------------------------------------------- #
# Section: GitHub
# --------------------------------------------------------------------------- #
def check_github() -> dict:
    res: dict = {"available": False}
    rc, _, _ = _run(["gh", "auth", "status"], timeout=20)
    if rc != 0:
        return res
    res["available"] = True
    rc, out, _ = _run(
        ["gh", "issue", "list", "--state", "open", "--json",
         "number,title,labels,updatedAt", "--limit", "50"],
        timeout=40,
    )
    if rc == 0:
        try:
            issues = json.loads(out)
        except json.JSONDecodeError:
            issues = []
        res["open_issues"] = [
            {"number": i["number"], "title": i["title"],
             "labels": [l["name"] for l in i.get("labels", [])]}
            for i in issues
        ]
    # Failed CI runs (last day)
    rc, out, _ = _run(
        ["gh", "run", "list", "--status", "failure", "--limit", "10", "--json",
         "number,headBranch,createdAt,displayTitle"],
        timeout=40,
    )
    if rc == 0:
        try:
            res["failed_runs"] = json.loads(out)
        except json.JSONDecodeError:
            res["failed_runs"] = []
    return res


# --------------------------------------------------------------------------- #
# Section: Financial-safety invariant verification (static, evidence-based)
# --------------------------------------------------------------------------- #
def verify_financial_safety(report: Report) -> dict:
    """Static verification of the BUG->TRADE->LOSS guard rails (ADRs).

    We grep the source for the exact guard patterns and record file:line
    evidence. This is the 'prove the path is impossible or mitigated' step from
    the brief's security audit (section 13). We do NOT modify trading logic.
    """
    checks = []

    def _find(pattern: str, path: str) -> Optional[str]:
        p = ROOT / path
        if not p.exists():
            return None
        rx = re.compile(pattern)
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if rx.search(line):
                return f"{path}:{i}"
        return None

    # ADR-008: missing bid/ask fails closed (reject before risk/broker)
    c = _find(r"SPREAD GUARD: Missing or invalid Bid/Ask|MISSING_BID_ASK", "src/monitor.py")
    checks.append(("missing_bid_ask_fails_closed", c))

    # PAPER shadow never places broker opens (BrokerageService._pre_submit_gate)
    c = _find(r"PAPER_TRADING.*broker submit blocked|broker submit blocked.*PAPER", "src/services/brokerage_service.py")
    checks.append(("paper_shadow_blocks_broker_opens", c))

    # LIVE_CAPITAL_DANGER required for real submits
    c = _find(r"LIVE_CAPITAL_DANGER is false", "src/services/brokerage_service.py")
    checks.append(("live_capital_danger_enforced", c))

    # Exactly-once intent (duplicate order protection) in execute_trade
    c = _find(r"EXACTLY-ONCE", "src/monitor.py")
    checks.append(("exactly_once_duplicate_protection", c))

    # Ambiguous submit -> requires_reconciliation (ADR-003)
    c = _find(r"requires_reconciliation", "src/services/brokerage/alpaca.py")
    checks.append(("ambiguous_submit_flagged", c))

    # Capital halt blocks new opens (ADR-005/011)
    c = _find(r"operational_status", "src/services/capital_halt_service.py")
    checks.append(("capital_halt_present", c))

    missing = [name for name, loc in checks if loc is None]
    res = {"checks": {name: (loc or "NOT FOUND") for name, loc in checks},
           "all_present": not missing}
    if missing:
        report.add(
            Finding(
                "HIGH", "Financial-safety guard could not be verified in source",
                f"missing static evidence for: {', '.join(missing)}",
                "FinancialSafety", requires_review=True,
                evidence="scripts/daily_bot_audit.verify_financial_safety",
            )
        )
    else:
        report.add(
            Finding(
                "INFO", "Financial-safety guard rails present (static verification)",
                "All BUG->TRADE->LOSS guard patterns located with file:line evidence",
                "FinancialSafety", evidence="; ".join(f"{n}={l}" for n, l in checks),
            )
        )
    return res


# --------------------------------------------------------------------------- #
# Section: .env / mode safety configuration check (fail-closed guardrails)
# --------------------------------------------------------------------------- #
def check_env_safety(report: Report) -> dict:
    """Verify the local .env does not silently enable dangerous modes.

    We read only non-secret keys. Findings here are REQUIRES_REVIEW, never
    auto-fixed, because changing trading mode / risk is outside the audit's
    safe envelope.
    """
    res: dict = {"checked": False}
    if not ENV_PATH.exists():
        res["note"] = "no .env in repo (CI uses injected secrets)"
        return res
    vals: dict[str, str] = {}
    for raw in ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip().strip('"').strip("'")
    res["checked"] = True
    paper = vals.get("PAPER_TRADING", "true").lower() in ("1", "true", "yes")
    live_danger = vals.get("LIVE_CAPITAL_DANGER", "false").lower() in ("1", "true", "yes")
    provider = vals.get("BROKERAGE_PROVIDER", "ALPACA").upper()
    base_url = vals.get("ALPACA_BASE_URL", "")

    # Rule 1: live (non-paper) submit requires LIVE_CAPITAL_DANGER.
    if not paper and not live_danger:
        report.add(
            Finding(
                "HIGH", "Non-paper mode without LIVE_CAPITAL_DANGER guard",
                "PAPER_TRADING=false but LIVE_CAPITAL_DANGER != true — code refuses this, "
                "but the config is mis-set and must be corrected by an operator",
                "Config", requires_review=True,
                evidence=".env PAPER_TRADING / LIVE_CAPITAL_DANGER",
            )
        )
    # Rule 2: broker forced to ALPACA.
    if provider != "ALPACA":
        report.add(
            Finding(
                "MEDIUM", "Non-Alpaca BROKERAGE_PROVIDER set",
                f"BROKERAGE_PROVIDER={provider} — runtime forces ALPACA; legacy providers are disabled",
                "Config", requires_review=True, evidence=".env BROKERAGE_PROVIDER",
            )
        )
    # Rule 3: zscore floor.
    try:
        z = float(vals.get("MONITOR_ENTRY_ZSCORE", "2.0"))
        if z < 1.0:
            report.add(
                Finding("HIGH", "MONITOR_ENTRY_ZSCORE below safe minimum",
                        f"z={z} (<1.0) — runtime clamps this, but config is unsafe",
                        "Config", requires_review=True, evidence=".env MONITOR_ENTRY_ZSCORE")
            )
    except ValueError:
        pass
    res.update({"paper": paper, "live_danger": live_danger, "provider": provider,
                "base_url": base_url, "zscore": vals.get("MONITOR_ENTRY_ZSCORE")})
    return res


# --------------------------------------------------------------------------- #
# Section: Known open issues (from GitHub) -> classification
# --------------------------------------------------------------------------- #
def classify_open_issues(report: Report, issues: list[dict]) -> None:
    """Emit a finding per open issue with auto-fix vs REQUIRES_REVIEW call.

    Per the project's safety posture, none of the currently-open issues are
    safe auto-fix code bugs — they are ops/key/config/toolchain, so they are
    all REQUIRES_REVIEW. This is evidence-based, not assumed.
    """
    # Map known issue numbers -> why REQUIRES_REVIEW (from manual triage).
    reasons = {
        111: "ops: Gemini API key unblock is a Google Cloud action, not a code fix",
        109: "ops: equity admit knobs are risk-relevant; rollback is an operator decision",
        102: "ops: PAIR_DISCOVERY pin is a risk decision pending OOM/RSS soak proof",
        91: "parked feature: reactivate only with fresh cache + veto/telemetry tests",
        57: "test: Java toolchain (gradle/DinD) not available here; not a code bug",
    }
    for i in issues:
        n = i["number"]
        report.requires_review.append(
            f"#{n} {i['title']} — {reasons.get(n, 'manual triage required')}"
        )
        report.add(
            Finding(
                "MEDIUM" if n in (109, 102) else "LOW",
                f"Open issue #{n}: {i['title']}",
                reasons.get(n, "manual triage required"),
                "GitHub", requires_review=True,
            )
        )


# --------------------------------------------------------------------------- #
# Section: Trend (vs previous daily report)
# --------------------------------------------------------------------------- #
def compute_trend(report: Report) -> dict:
    prev = None
    if LATEST_REPORT.exists():
        txt = LATEST_REPORT.read_text(encoding="utf-8", errors="replace")
        # crude metric extraction (numeric after labels)
        def _grab(label: str) -> Optional[float]:
            m = re.search(rf"{label}:\s*([0-9.]+)", txt)
            return float(m.group(1)) if m else None
        prev = {
            "errors": _grab("Errors"),
            "incidents": _grab("Incidents"),
            "api_degraded": _grab("API degraded"),
            "expected_fail_closed": _grab("Expected fail-closed"),
        }
    cur = report.sections.get("logs", {})
    trend: dict[str, Any] = {"previous": prev, "current": {}}
    mapping = {
        "Errors": cur.get("levels", {}).get("ERROR", 0),
        "Incidents": len(cur.get("incidents", [])),
        "API degraded": cur.get("api_degraded_hits", 0),
        "Expected fail-closed": cur.get("expected_fail_closed", 0),
    }
    trend["current"] = mapping
    if prev:
        for k, v in mapping.items():
            pv = prev.get(k.lower().replace(" ", "_"))
            if pv is not None and isinstance(v, (int, float)):
                delta = v - pv
                if delta > 0 and k in ("Errors", "Incidents"):
                    report.add(
                        Finding(
                            "MEDIUM", f"Metric worsening vs previous audit: {k}",
                            f"{k} went {pv} -> {v} (+{delta})",
                            "Trend", requires_review=(k == "Incidents"),
                        )
                    )
    return trend


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #
def render_report(report: Report) -> str:
    L: list[str] = []
    L.append("# BOT DAILY AUDIT")
    L.append("")
    L.append(f"Date: {report.date}")
    L.append(f"Commit: {report.commit}")
    L.append(f"Environment: {report.environment}")
    L.append(f"Runtime: {report.runtime_health}")
    L.append(f"Health: {report.verdict}")
    L.append("")
    L.append("## CRITICAL")
    crit = [f for f in report.findings if f.severity == "CRITICAL"]
    L.append("\n".join(f.to_md() for f in crit) or "- (none)")
    L.append("")
    L.append("## WARNINGS (HIGH/MEDIUM/LOW)")
    warn = [f for f in report.findings if f.severity in ("HIGH", "MEDIUM", "LOW")]
    L.append("\n".join(f.to_md() for f in warn) or "- (none)")
    L.append("")
    # Trading
    L.append("## TRADING")
    tr = report.sections.get("trading", {})
    if tr.get("reachable"):
        L.append(f"- Positions/Orders/PnL: see dashboard API at {tr.get('host')}")
        L.append(f"- Health: {json.dumps(tr.get('health', {}))[:200]}")
    else:
        L.append(f"- Bot API not reachable from this host ({tr.get('reason', 'n/a')}); "
                 "trading checks run on bot-server.")
    L.append("")
    # Infrastructure / Runtime
    L.append("## INFRASTRUCTURE")
    rt = report.sections.get("runtime", {})
    L.append(f"- Running: {rt.get('running')} (detected at: {rt.get('where')})")
    if rt.get("details"):
        L.append(f"- Details: {json.dumps(rt['details'])}")
    L.append(f"- Disk: audit host free space unknown in this pass (bot-server ops check covers it)")
    L.append("")
    # Log analysis
    L.append("## LOG ANALYSIS")
    lg = report.sections.get("logs", {})
    L.append(f"- Total log lines: {lg.get('total_lines')}")
    L.append(f"- Window lines: {lg.get('window_lines')}")
    L.append(f"- Levels: {json.dumps(lg.get('levels', {}))}")
    L.append(f"- Expected fail-closed (correct safety behavior): {lg.get('expected_fail_closed')}")
    L.append(f"- API degraded hits: {lg.get('api_degraded_hits')}")
    L.append(f"- Real incidents (crash/OOM/dup/unknown-exposure): {len(lg.get('incidents', []))}")
    L.append("")
    # Tests
    L.append("## TESTS")
    sw = report.sections.get("software", {})
    if sw.get("skipped"):
        L.append("- (skipped this run)")
    else:
        L.append(f"- Bug-hunt preflight: {'PASS' if sw.get('bug_hunt', {}).get('passed') else 'FAIL'} "
                 f"(rc={sw.get('bug_hunt', {}).get('rc')})")
        L.append(f"- Ruff: {'PASS' if sw.get('ruff', {}).get('passed') else 'FAIL'} "
                 f"(rc={sw.get('ruff', {}).get('rc')})")
        pt = sw.get("pytest", {})
        L.append(f"- Pytest ({sw.get('mode')}): {'PASS' if pt.get('passed') else 'FAIL'} — {pt.get('summary', '')}")
        L.append(f"- Uncollectable (env, not code): {len(pt.get('uncollectable_reported', []))} modules")
    L.append("")
    # GitHub
    L.append("## GITHUB")
    gh = report.sections.get("github", {})
    if not gh.get("available"):
        L.append("- gh CLI unavailable in this env; GitHub checks run in CI / on bot-server.")
    else:
        L.append(f"- Open issues: {len(gh.get('open_issues', []))}")
        L.append(f"- Failed CI runs (last): {len(gh.get('failed_runs', []))}")
        for i in gh.get("open_issues", [])[:15]:
            L.append(f"  - #{i['number']} {i['title']} [{','.join(i['labels'])}]")
    L.append("")
    # Financial safety
    L.append("## FINANCIAL SAFETY (static verification)")
    fs = report.sections.get("financial_safety", {})
    for name, loc in fs.get("checks", {}).items():
        L.append(f"- {name}: `{loc}`")
    L.append("")
    # Config / mode safety
    L.append("## CONFIG / MODE SAFETY")
    cf = report.sections.get("config", {})
    if not cf.get("checked"):
        L.append(f"- {cf.get('note', 'not checked')}")
    else:
        L.append(f"- PAPER_TRADING={cf.get('paper')}  LIVE_CAPITAL_DANGER={cf.get('live_danger')}  "
                 f"BROKERAGE_PROVIDER={cf.get('provider')}  MONITOR_ENTRY_ZSCORE={cf.get('zscore')}")
    L.append("")
    # Auto fixes
    L.append("## AUTOMATIC FIXES")
    L.append("\n".join(f"- {x}" for x in report.fixes_applied) or "- (none applied this run)")
    L.append("")
    # Requires review
    L.append("## REQUIRES REVIEW")
    L.append("\n".join(f"- {x}" for x in report.requires_review) or "- (none)")
    L.append("")
    # Trend
    L.append("## HISTORICAL TREND")
    trd = report.trend
    L.append(f"- Previous: {json.dumps(trd.get('previous'))}")
    L.append(f"- Current: {json.dumps(trd.get('current'))}")
    L.append("")
    L.append("## OVERALL VERDICT")
    L.append(report.verdict)
    L.append("")
    L.append(f"_generated: {_now_iso()}_")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def run_audit(date: str, tests_mode: str, no_github: bool, no_autofix: bool) -> Report:
    report = Report(
        date=date,
        commit=_git_commit(),
        environment=_env_label(),
        runtime_health="unknown",
    )

    # Runtime
    rt = check_runtime()
    report.sections["runtime"] = rt
    report.runtime_health = (
        "UP" if rt.get("running") else "NOT-RUNNING-HERE (bot is on bot-server)"
    )

    # Logs
    lg = analyze_logs(report)
    report.sections["logs"] = lg

    # Trading
    report.sections["trading"] = check_trading()

    # Software
    report.sections["software"] = run_tests(tests_mode)

    # GitHub
    gh = {} if no_github else check_github()
    report.sections["github"] = gh
    if gh.get("available"):
        classify_open_issues(report, gh.get("open_issues", []))
        failed = gh.get("failed_runs", []) or []
        if failed:
            recent = "; ".join(
                f"#{r.get('number')} {r.get('headBranch')}" for r in failed[:8]
            )
            report.add(
                Finding(
                    "MEDIUM", f"{len(failed)} failed CI run(s) in recent history",
                    f"Recent failed workflows: {recent}",
                    "GitHub", requires_review=True,
                    evidence="gh run list --status failure",
                )
            )

    # Financial safety static verification
    report.sections["financial_safety"] = verify_financial_safety(report)

    # .env / mode safety configuration check
    report.sections["config"] = check_env_safety(report)

    # Auto-remediation (safe, guarded) — disabled by default in CI to stay
    # read-only; enabled locally with an explicit flag.
    if not no_autofix:
        from scripts.audit_remediations import (
            RemediationState, discover_safe_fixes, apply_with_guard,
        )
        state = RemediationState.load()
        candidates = discover_safe_fixes()
        applied = 0
        for fix in candidates:
            if applied >= 5:
                break
            allowed, reason = state.can_apply(fix.signature)
            if not allowed:
                report.requires_review.append(
                    f"auto-fix {fix.signature} skipped: {reason}"
                )
                continue
            ok, msg = apply_with_guard(fix, state)
            if ok:
                report.fixes_applied.append(f"{fix.title} ({fix.signature})")
                applied += 1
            else:
                report.add(
                    Finding("LOW", f"Auto-remediation could not be applied: {fix.title}",
                            msg.splitlines()[0], "AutomaticFixes",
                            requires_review=True)
                )

    # Trend
    report.trend = compute_trend(report)

    # Verdict
    sev = report.highest_severity()
    if sev in ("CRITICAL",):
        report.verdict = "CRITICAL"
    elif sev in ("HIGH", "MEDIUM"):
        report.verdict = "DEGRADED"
    else:
        report.verdict = "HEALTHY"

    # Persist
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{date}.md"
    rendered = render_report(report)
    path.write_text(rendered, encoding="utf-8")
    LATEST_REPORT.write_text(rendered, encoding="utf-8")
    return report


def _env_label() -> str:
    rc, branch, _ = _run(["git", "-C", str(GIT), "rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch.strip() or "unknown"
    # Detect CI
    if "GITHUB_ACTIONS" in __import__("os").environ:
        return f"ci:{branch}"
    return f"local:{branch}"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Daily Bot Audit for bot-trading")
    ap.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--tests", choices=["fast", "full", "none"], default="fast")
    ap.add_argument("--no-github", action="store_true")
    ap.add_argument("--autofix", action="store_true", default=False,
                    help="ENABLE safe, guarded auto-remediation (opt-in; "
                         "default is OFF / fully read-only)")
    args = ap.parse_args(argv)

    report = run_audit(args.date, args.tests, args.no_github, not args.autofix)
    print(render_report(report))
    print(f"\nReport written to: reports/daily-audit/{args.date}.md", file=sys.stderr)
    return {"HEALTHY": 0, "DEGRADED": 1, "CRITICAL": 2}[report.verdict]


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(3)
