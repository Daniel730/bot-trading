# Daily Bot Audit — Continuous Autonomous Maintenance

This document describes the **Daily Bot Audit** system for `bot-trading`. It was
built to operationalize continuous, evidence-based maintenance on top of the
project's *existing* audit machinery (the `.brain/` ledgers, `docs/AUDIT_*`,
`scripts/full_day_audit_*.py` soak sampler/analyzer, and `infra/ops_*_check.sh`
ops scripts). It does **not** replace them; it orchestrates and consolidates
them into one reproducible, versioned, observable daily report.

> **Safety posture (read this first).** This bot is a financial system. The
> audit is strictly **read-mostly**. It never places or cancels orders, never
> flips `PAPER_TRADING`, never changes sizing/risk limits, never touches
> credentials or broker endpoints. Anything that could affect capital is emitted
> as a `REQUIRES_REVIEW` finding and left for a human. Auto-remediation is
> limited to safe, reversible hygiene (creating output dirs, rotating an empty
> dead `monitor.out`, maintaining the `latest.md` pointer) and is **opt-in**
> (`--autofix`). By default the audit is fully non-destructive.

---

## 1. What it checks

| Section | Source | Notes |
|---|---|---|
| **Runtime** | `docker`/`pgrep` probe | Detects bot on this host; honestly reports "not-running-here" on dev/CI. Real runtime checks belong to `infra/ops_overnight_check.sh` on bot-server. |
| **Logs** | `logs/structured_logs.jsonl` | Pattern rules distinguish **expected fail-closed safety behavior** (reconciliation, emergency closes, exactly-once refusals) from **real incidents** (Traceback/OOM/duplicate-fill/unknown-exposure). Naive `ERROR` counting is explicitly avoided. |
| **Trading** | dashboard API `:8080` | Best-effort positions/orders/PnL if the bot API is reachable from the audit host; otherwise reports unavailable. |
| **Software** | `pytest` + `ruff` + `bug_hunt_audit.py` | Mirrors the CI gate (`ci.yml`): broker/config safety contract tests, ruff undefined-names, the existing secret-hygiene preflight. |
| **GitHub** | `gh` CLI | Open issues (auto-classified), failed CI runs, PRs, dependabot. |
| **Financial Safety** | static source grep | Verifies the BUG→TRADE→LOSS guard rails (ADR-003/006/008/010/012) with `file:line` evidence. Proves the path is mitigated, not assumed safe. |
| **Trend** | previous `latest.md` | Errors / incidents / API-degraded / expected-fail-closed compared to the prior run. |
| **Auto-fixes / Requires Review** | remediation module | Safe fixes applied (opt-in) with anti-loop guards; everything else listed for humans. |

---

## 2. How to run it

### Locally (manual)

```bash
cd bot-trading
# fast safety gate (bug_hunt + ruff + quick broker/config tests): ~2-6 min
PYTHONPATH=. .venv/Scripts/python.exe scripts/daily_bot_audit.py --tests fast

# full (adds the heavy monitor_execution/closing safety tests): ~10 min
PYTHONPATH=. .venv/Scripts/python.exe scripts/daily_bot_audit.py --tests full

# enable safe hygiene auto-remediation (opt-in)
PYTHONPATH=. .venv/Scripts/python.exe scripts/daily_bot_audit.py --autofix

# skip GitHub (e.g. no token)
PYTHONPATH=. .venv/Scripts/python.exe scripts/daily_bot_audit.py --no-github
```

**Environment overrides** (so the audit runs where the bot actually lives):

| Var | Default | Purpose |
|---|---|---|
| `AUDIT_LOG_PATH` | `logs/structured_logs.jsonl` | Where the structured log lives (e.g. `/app/logs/structured_logs.jsonl` in-container). |
| `APP_ENV_FILE` | `repo/.env` | Real env file on bot-server (`/home/daniel/.env.trading`); `check_env_safety` reads this. |
| `AUDIT_ENV_PATH` | `APP_ENV_FILE` or `repo/.env` | Explicit override of the env file. |
| `AUDIT_BOT_HOST` | `http://127.0.0.1:8082` | Dashboard API base (port 8082 on bot-server, 8080 locally). |

Exit code: `0` healthy, `1` degraded, `2` critical — useful for cron gating.

### Automatically (daily)

`.github/workflows/daily-audit.yml` runs it on a daily cron (`17 6 * * *` UTC)
and via **manual dispatch** (choose `tests` scope and whether to allow
`--autofix`). The job:

- installs from `requirements.lock` (so the audit runs in the project's real env),
- runs read-only by default (no `--autofix`, no live secrets),
- uploads `reports/daily-audit/` as a build artifact,
- annotates the run when the verdict is `DEGRADED`/`CRITICAL`.

> On bot-server (the real runtime host) the audit is best paired with the
> existing `infra/ops_overnight_check.sh`, which covers container restarts,
> OOM, cgroup limits, and in-container runtime state that this audit cannot see
> from a dev/CI host.

**bot-server integration.** `infra/ops_overnight_check.sh` now invokes the
audit at the end of its run (read-only, `--tests none --no-autofix`) inside the
`trading-bot-bot-1` container, using `AUDIT_LOG_PATH` / `APP_ENV_FILE` from the
deploy environment. The audit's own report is written to
`reports/daily-audit/YYYY-MM-DD.md` inside the container; mount or copy that
path if you want it persisted off-host. The ops check never fails on a non-zero
audit exit — the audit is best-effort observability layered on top of the ops
check.

---

## 3. Report format

Reports are written to `reports/daily-audit/YYYY-MM-DD.md` **and** a
`latest.md` pointer (the latter is just a copy, so re-running is idempotent).
The schema follows the brief:

```text
BOT DAILY AUDIT
Date / Commit / Environment / Runtime / Health
CRITICAL        - ...
WARNINGS        - ... (HIGH/MEDIUM/LOW)
TRADING         - positions/orders/PnL or "not reachable"
INFRASTRUCTURE  - running?, details, disk
LOG ANALYSIS    - total/window lines, levels, expected-fail-closed, API-degraded, incidents
TESTS           - bug_hunt, ruff, pytest summary, uncollectable (env) count
GITHUB          - open issues, failed CI runs
FINANCIAL SAFETY - guard: file:line evidence
AUTOMATIC FIXES - what was applied (empty by default)
REQUIRES REVIEW - human actions
HISTORICAL TREND - previous vs current metric snapshot
OVERALL VERDICT - HEALTHY / DEGRADED / CRITICAL
```

### Interpreting the verdict

- **HEALTHY** — no CRITICAL/HIGH/MEDIUM findings.
- **DEGRADED** — HIGH or MEDIUM findings exist (e.g. open risk-relevant ops
  issues #102/#109, or a worsening metric). Trading is not blocked, but a human
  should look.
- **CRITICAL** — a real incident pattern (crash/OOM/duplicate-fill/unknown
  exposure) was detected in the audit window, or a financial-safety guard could
  not be verified in source. Stop and triage.

### Reading "expected fail-closed"

A large `Expected fail-closed` count is **good**, not bad: it means the bot is
correctly refusing to trade when state is ambiguous (ADR-003/011/012). The audit
only escalates lines that match the `_INCIDENT` pattern (Traceback, OOM,
duplicate fill, unknown exposure, restart loop).

---

## 4. Auto-remediation policy

Defined in `scripts/audit_remediations.py`. Principles:

1. **Non-financial & reversible only.** No trading-mode, risk, sizing,
   credential, endpoint, or capital change is ever auto-applied.
2. **Idempotent.** Running twice with no change is a no-op.
3. **Validated.** Every fix has a `validate()` step; on failure the orchestrator
   calls `restore()` and reverts (no half-fixes).
4. **Anti-loop guards** (persisted in `data/audit/remediation_state.json`):
   - max **5 fixes per run**,
   - per-signature **24h cooldown**,
   - per-signature **3-attempt cap** → after that, escalate to `REQUIRES_REVIEW`
     and stop trying.
5. **Opt-in.** Default run is `--no-autofix`. The GitHub Action never enables it.

Current safe fixes:
- `ensure_audit_dirs` — create missing `reports/daily-audit` / `data/audit/logs`.
- `rotate_empty_monitor_out` — move aside a 0-byte `monitor.out` left by a
  crashed sampler, only when no monitor process is running.

If a fix's `validate()` fails, the change is reverted and the signature is
recorded so it won't be retried inside the cooldown.

---

## 5. `REQUIRES_REVIEW` criteria

A finding is marked `REQUIRES_REVIEW` when it could affect capital, availability,
or is outside the audit's safe-change envelope. Concretely:

- Any GitHub issue that is ops/key/config/toolchain (currently **all 5 open
  issues** — #111 Gemini key, #109 equity knobs, #102 discovery pin, #91 whale
  watcher park, #57 Java toolchain).
- A real incident pattern in the log window.
- A financial-safety guard that cannot be located in source.
- A worsening metric (incidents/errors up vs previous run).
- A failed auto-remediation that could not be validated.

These are never auto-fixed. The audit lists them and a human decides.

---

## 6. Rollback / troubleshooting

- **Audit produced no report?** Check `reports/daily-audit/` exists and that the
  process had write access. The audit always writes before exiting.
- **`pytest` timed out / uncollectable modules?** Ten test modules require
  optional Linux-only deps (`grpc`, `edgar`) unavailable on this Windows venv.
  They are reported under "Uncollectable (env, not code)" and excluded from the
  pass/fail count — they are **not** counted as failures. Run them on a
  Docker-capable Linux host (CI) for full coverage.
- **False `CRITICAL` on logs?** The `_INCIDENT` regex is in `analyzze_logs`. If a
  new benign pattern triggers it, add it to `_EXPECTED_FAIL_CLOSED` with evidence
  and a test in `tests/unit/test_daily_bot_audit.py`.
- **Accidental auto-fix?** Auto-fix is opt-in and each fix is reversible
  (`restore`). To disable entirely, run with `--no-autofix` (the default). State
  lives in `data/audit/remediation_state.json`; delete it to reset the guards.

---

## 7. Extending the audit

- **New log pattern?** Add to `_EXPECTED_FAIL_CLOSED` / `_INCIDENT` /
  `_API_DEGRADED` in `daily_bot_audit.py` and cover it with a test.
- **New safe fix?** Add a discovery function in `audit_remediations.py`
  returning a `Fix` with `apply`/`validate`/`restore`. Keep it non-financial.
- **New GitHub check?** Extend `check_github()`; the orchestrator already
  classifies open issues via `classify_open_issues()`.

All changes to the audit must keep the safety invariants in §0 and ship with a
test in `tests/unit/test_daily_bot_audit.py`.
