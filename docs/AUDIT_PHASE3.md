# Audit Phase 3 — Production Readiness

**Date:** 2026-08-04  
**Scope:** Final production-readiness audit after Phase-1/2 remediations.  
**Mandate:** Resolve F-015, F-020, Telegram LIVE without mandatory 2FA, F-023, F-025. Attempt to break every fix. Prove core invariants under failure. Deliver scores + one verdict.

---

## Executive Summary

Phase-3 closed the two absolute LIVE blockers called out by the operator (F-015 concurrent opens, F-020 crash-safe persistence/WAL) plus the authorization gap class (Telegram LIVE trade approve / `/invest`, pairs mutation without step-up, TOTP storage).

Adversarial tests (15+ Phase-3 unit cases) demonstrate:

- Concurrent slot claims → **exactly one** winner for the same legs / under `MAX_OPEN_PAIRS`.
- Intent WAL CLAIM/RELEASE is append-only, checksummed, idempotent on replay after “crash”.
- SQLite `journal_mode=WAL` + `BEGIN IMMEDIATE` budget increments survive threaded races.
- LIVE Telegram **trade** Approve is refused while **login** Approve still works.
- LIVE `/invest` and DCA schedule via Telegram are refused (dashboard + 2FA required).
- Pairs mutate / discover require step-up when 2FA enrolled.
- TOTP secrets use Fernet AEAD; backup codes salted HMAC; legacy XOR/SHA migrate.

**Final verdict: READY FOR PAPER TRADING ONLY.**

F-015/F-020 are no longer absolute blockers for **paper** (shadow or Alpaca paper). They are **not** yet proven under multi-process / multi-host LIVE. Remaining failure classes (broker mid-leg crash windows, realized-PnL-only drawdown, single-chat Telegram trust, WS frame limits) still forbid limited or full live capital.

---

## Production Readiness Score

| Dimension | Score | Notes |
|---|---|---|
| **Security** | **7.8 / 10** | Step-up parity for REST/terminal/pairs; LIVE Telegram trade approve closed; TOTP Fernet. Chat-id Telegram trust remains. |
| **Reliability** | **7.8 / 10** | SQLite WAL + atomic budget; intent WAL; single-process reservation. Multi-replica lock still open. |
| **Trading Safety** | **8.0 / 10** | Slot claim before approval; broker gate; lane snapshot; LIVE Telegram capital paths refused. |
| **Recoverability** | **7.5 / 10** | ORDER_SUBMITTED pre-Leg-A + reservation WAL replay; Leg B orphan window thinner but present. |
| **Observability** | **7.0 / 10** | Audit logs for refused LIVE Telegram; decision recorder stages; no full crash-injection telemetry suite. |
| **Determinism** | **6.5 / 10** | Replay/idempotency properties for WAL/budget; historical multi-run identity not fully harnessed this phase. |
| **Maintainability** | **7.5 / 10** | Reservation service isolated; docs updated; residual debt catalogued (not mass-refactored). |

Overall posture: **paper-capable with high confidence; LIVE capital still blocked by residual classes**, not by missing F-015/F-020 alone.

---

## Highest-priority remediations

### [F-015] Critical → Closed (single-process)

**Problem:** Concurrent approvals could both see an empty ledger and double-open.

**Fix:** `OpenSlotReservationService` claims pair/leg slots **before** `request_approval`, holds through `execute_trade`, releases in `finally`. Reservations merge into book guards (`_has_active_pair_or_pending_order`, execute_trade lane checks).

**WAL:** Append-only JSONL (`data/audit/open_slot_reservations.wal`) with SHA-256 checksums, fsync per record, CLAIM/RELEASE replay.

**Break attempts:**
| Attack | Result |
|---|---|
| 12 concurrent claims same pair | 1 win / 11 lose |
| Shared leg second claim | `shared_leg_guard` |
| Max open pairs with concurrent newcomers | Cap respected |
| Idempotent re-claim same `signal_id` | `already_held` |
| Dual process without shared lock | **Residual** — in-process `asyncio.Lock` only |

### [F-020] Critical → Closed (SQLite + intent WAL)

**Problem:** Default SQLite journal + non-atomic budget reads → torn state / lost increments under crash/concurrency.

**Fix:**
- `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`
- `BEGIN IMMEDIATE` on `set_system_state` / `increment_system_state_float`
- `BudgetService.update_used_budget` uses atomic increment
- Trade-intent WAL (same file as F-015) for open reservations

**Break attempts:**
| Attack | Result |
|---|---|
| Tampered WAL checksum | Record skipped |
| Corrupt JSONL line | Skipped; good records kept |
| Crash after CLAIM | Replay restores reservation (fail-closed hold until TTL/RELEASE) |
| 50 threaded budget +1 | Final == 50.0 |
| Kill -9 mid-fsync | OS-dependent; WAL + fsync designed for power-loss of completed records |

### Telegram LIVE without mandatory 2FA → Closed (trade path)

**Problem:** Inline Approve / `/invest` could authorize LIVE with chat-id only.

**Fix:**
- Trade Approve (`cid` in `pending_approval_summaries`) refused when `not should_auto_approve_trades`
- Login Approve (not in summaries) still allowed
- LIVE `/invest` and LIVE DCA `schedule` refused → dashboard + step-up

**Break attempts:**
| Attack | Result |
|---|---|
| Telegram Approve on LIVE trade | Refused; Future stays open for dashboard 2FA |
| Telegram Approve on login challenge | Still succeeds |
| LIVE `/invest … confirm` | Hard refuse |
| Broker-paper auto-approve lane | Unchanged (expected) |

### [F-023] Medium → Closed

`POST /api/pairs` and `POST /api/pairs/discover` call `require_step_up_2fa`. UI prompts OTP on 403.

### [F-025] Medium → Closed

Fernet (`fernet:` prefix) with `TOTP_ENCRYPTION_KEY` or derived `DASHBOARD_TOKEN`; salted `salt$hmac` backups; legacy XOR/SHA still verify and migrate.

---

## Core invariants — status

| Invariant | Status | Evidence / residual |
|---|---|---|
| Signal → ≤1 broker order | **Strengthened** | Reservation + client_order_id; multi-process residual |
| Order ↔ one strategy | **Held** (ledger design) | No Phase-3 contradiction found |
| Position never duplicated | **Strengthened** | Shared-leg + slot claim |
| Position state never backwards | **Held** (state machine) | Not exhaustively fuzzed |
| Close never reopens | **Held** | Close intent bypasses halt only |
| Partial fills ≠ duplicate exposure | **Partial** | F-024 still open (sizing from Leg A) |
| Capital ≤ limits | **Strengthened** | Budget atomic + halt gate |
| Daily halt / drawdown | **Partial** | Realized-PnL-only drawdown remains design limit |
| Emergency stop all paths | **Partial** | Broker gate covers opens; not every sidecar |
| Shadow never LIVE orders | **Held** | Gate + PAPER_TRADING |
| Legacy never fabricates broker | **Held** | F-009 |
| LIVE needs fresh auth | **Strengthened** | Dashboard 2FA; Telegram trade approve closed |
| Privileged = authenticated identity | **Strengthened** | Pairs/discover step-up |
| Channel auth parity | **Improved** | LIVE trade Telegram no longer weaker than REST |
| Secrets not in logs | **Held** | Redaction; TOTP ciphertext upgraded |
| Crash stages → no dup/lost/corrupt | **Improved** | WAL + ORDER_SUBMITTED; Leg B window residual |

---

## Crash / failure injection (documented behavior)

| Failure | Behavior |
|---|---|
| Crash before signal accepted | No CLAIM; no order |
| Crash after CLAIM, before approve | Reservation held until TTL; pair blocked (fail-closed) |
| Crash after ORDER_SUBMITTED, before Leg A ack | Startup reconciler watches `ORDER_SUBMITTED` |
| Crash between Leg A and Leg B | Pre-existing orphan risk; not fully closed |
| Crash after fill, before RELEASE | Reservation may over-count until TTL (fail-closed) |
| Redis down | Monitor/deps may degrade; reservation WAL is filesystem |
| Filesystem full on WAL append | Claim fails closed (exception path) |
| JSON WAL corruption | Bad lines skipped |
| SIGTERM | Finally releases when unwind runs; SIGKILL skips finally → TTL |
| Alpaca API error | Broker returns error; budget not accrued on failure paths |
| Clock skew | TOTP window ±30s; reservation TTL wall-clock |

---

## Concurrency stress

| Scenario | Result |
|---|---|
| Simultaneous slot claims | One winner (asyncio lock) |
| Duplicate CLAIM same signal | Idempotent |
| Concurrent budget increments | Atomic SQLite |
| Concurrent REST pairs without OTP | 403 when 2FA on |
| Concurrent Telegram Approve LIVE | Each refused independently |
| Multi-worker / multi-host | **Not proven** — needs Redis/DB advisory lock |

---

## Property / fuzz coverage (Phase-3)

- Replay(CLAIM/RELEASE*) == live reservation set
- Duplicate messages / claims never exceed one reservation per signal
- Malformed claim payloads rejected
- WAL checksum + corrupt JSON skipped
- Budget never loses increments under thread race
- Backup codes single-use

Hypothesis library not installed; properties encoded as deterministic unit tests.

---

## Technical debt (risk-relevant only)

| Item | Risk | Action |
|---|---|---|
| Process-local reservation lock | Multi-replica double-open | Redis/Postgres advisory claim before LIVE multi-host |
| Realized-PnL-only drawdown | Mark-to-market bypass | Equity-curve halt |
| F-024 partial fill sizing | Asymmetric hedge | Always size Leg B from Leg A fill |
| F-026 unbounded WS frames | DoS | Frame size cap |
| Telegram chat-id trust | Compromised chat | Bind device / drop capital from Telegram entirely |
| Mutable globals / singletons | Test isolation | Accept for now; reservation service already injectable |

No broad refactor performed — only risk-reducing changes.

---

## Remaining Risks

### R-301 — Multi-process reservation gap
- **Severity:** High (LIVE multi-host)
- **Exploitability:** Medium (requires ≥2 workers racing)
- **Financial impact:** Duplicate opens / over `MAX_OPEN_PAIRS`
- **Operational impact:** Manual unwind
- **Mitigation:** Redis `SET NX` / Postgres advisory lock shared with WAL

### R-302 — Leg B crash orphan
- **Severity:** High
- **Exploitability:** Low (timing)
- **Financial impact:** One-legged exposure
- **Operational impact:** Reconciler / manual hedge
- **Mitigation:** Two-phase commit style Leg B plan + watchdog

### R-303 — Realized-PnL drawdown only
- **Severity:** High
- **Exploitability:** Market path (unrealized bleed)
- **Financial impact:** Breach of intended risk budget
- **Operational impact:** Halt triggers late
- **Mitigation:** Include unrealized / equity high-water mark

### R-304 — Telegram chat compromise (non-trade)
- **Severity:** Medium
- **Exploitability:** Medium if chat shared/leaked
- **Financial impact:** Login approve / info leak; trade approve blocked
- **Operational impact:** Session theft via login Approve
- **Mitigation:** Prefer TOTP-only login; disable Telegram login Approve for LIVE

### R-305 — Determinism / soak gaps
- **Severity:** Medium
- **Exploitability:** N/A (quality)
- **Financial impact:** Harder forensic replay
- **Operational impact:** Audit friction
- **Mitigation:** Historical replay harness with state hashes

### R-306 — F-024 / F-026 / MCP weak tokens
- **Severity:** Medium–Low
- **Exploitability:** Varies
- **Financial impact:** Hedge skew / DoS / tool abuse if weak MCP token
- **Mitigation:** Prior backlog items

---

## Final Verdict

# READY FOR PAPER TRADING ONLY

**Justification (objective):**

1. **Shadow / Alpaca paper:** Auto-approve lanes unchanged; broker gate refuses LIVE opens in shadow; F-015/F-020/F-023/F-025 harden paper ops without blocking them.
2. **LIVE capital:** Absolute blockers F-015/F-020 are closed for **single-process** deployments, but R-301–R-303 remain exploitable or financially material under realistic LIVE failure. Operator guidance stands: closing failure *classes* matters more than score inflation — scores ~7.8/8.0 still below a live-money bar.
3. **Not** `NOT READY FOR PAPER TRADING` — Phase-3 tests + prior soak/remediations support paper.
4. **Not** `READY FOR LIMITED LIVE CAPITAL` — multi-process reservation, Leg B orphans, and unrealized drawdown are not closed.

---

## Regression

| Suite | Result |
|---|---|
| `tests/unit/test_audit_phase3_remediations.py` | Pass |
| Phase-1/2 audit + dashboard API security + budget | Pass |
| Frontend `PairsPanel` vitest | Pass |

---

## Files (primary)

- `src/services/open_slot_reservation.py` (new)
- `src/monitor.py` (claim/release)
- `src/models/persistence.py` (SQLite WAL + atomic float)
- `src/services/budget_service.py`
- `src/services/notification_service.py` (LIVE Telegram)
- `src/services/dashboard_service.py` (F-023/F-025)
- `frontend/src/services/api.ts`, `PairsPanel.tsx`, `App.tsx`
- `tests/unit/test_audit_phase3_remediations.py`
