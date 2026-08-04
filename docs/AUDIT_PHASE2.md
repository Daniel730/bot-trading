# Audit Phase 2 — Security & Reliability

**Date:** 2026-08-04  
**Scope:** Independent second audit of `cursor/full-day-audit-f7a8` after Phase-1 remediations.  
**Posture:** Do not trust Phase-1 fixes; treat them as potentially incomplete. Adversarial re-verification + new findings F-014+.

---

## Executive Summary

Phase-1 closed the original Critical/High landmines for LIVE threshold auto-approve, DEV_MODE+broker, Alpaca hostname spoofing, MCP unauthenticated tools, and legacy invent-broker-close. Phase-2 proved several of those fixes were **path-incomplete**: capital halt only covered `Monitor.execute_trade`, and dashboard trade approval still had a **terminal `/approve` bypass** of F-010 step-up.

This phase remediated the highest-confidence bypasses and open items (F-004/F-007/F-014–F-022 subset), added regression tests, and documented residual risk (concurrent approvals, Telegram chat-auth, realized-PnL-only drawdown, TOTP storage).

| Score | Value | Notes |
|---|---|---|
| Overall security | **7.2 / 10** | Strong fail-closed auth; residual Telegram/session threat model |
| Reliability | **7.0 / 10** | Pre-submit ledger + broker gate; SQLite WAL still open (F-020) |
| Trading safety | **7.5 / 10** | Halt on all broker opens; lane snapshot; budget accrue on success |
| Confidence | **High** on remediations with tests; **Medium** on race F-015 (not fully fixed) |

---

## Phase-1 re-verification

| ID | Claimed | Phase-2 verdict | Residual |
|---|---|---|---|
| F-001 | Fixed | **Unbypassable** for LIVE threshold auto-approve | `/set_threshold` needed 2FA (fixed via F-014) |
| F-002 | Fixed | **Was incomplete** — only `execute_trade` | Fixed: broker `_pre_submit_gate`; PnL-unavailable fail-closed on broker |
| F-003 | Fixed | **Unbypassable** | — |
| F-005 | Fixed | **Unbypassable** | — |
| F-008 | Fixed | **Unbypassable** for tool auth | Weak tokens still accepted if non-placeholder |
| F-009 | Fixed | **Unbypassable** for invent-broker-close | Untagged live orphans close via shadow (ops risk) |
| F-010 | Fixed | **Was incomplete** — terminal bypass | Fixed: F-014 step-up on `/api/terminal/command` |

---

## Findings (Phase-2)

### [F-014] High — Authz (F-010 regression bypass)
**Impact:** Stolen dashboard session could `/approve` LIVE trades without OTP.  
**Exploit:** `POST /api/terminal/command` with `{"command":"/approve <cid>"}`.  
**Files:** `dashboard_service.py` terminal endpoint; `notification_service.handle_dashboard_command`.  
**Root cause:** Dedicated approve APIs got step-up; terminal bridge did not.  
**Fix applied:** Require `require_step_up_2fa` for `/approve`, `/reject`, `/set_threshold`; UI prompts OTP.

### [F-015] High — Race / concurrent opens
**Impact:** Multiple pairs can clear approval with empty ledger then both execute.  
**Exploit:** Concurrent scan approvals on shared legs / over `MAX_OPEN_PAIRS`.  
**Files:** `monitor.py` process_pair / execute_trade.  
**Root cause:** No in-flight reservation before `request_approval`.  
**Fix:** **Not fully implemented** this phase — documented; recommend Redis/DB slot claim.

### [F-016] / [F-007] High — Crash between place and ledger
**Impact:** Broker fill with no ledger row after crash.  
**Fix applied:** Persist `ORDER_SUBMITTED` with `client_order_id` **before** Leg A `place_*`; promote via `attach_broker_order_id`. Startup reconciler already watches `ORDER_SUBMITTED`.

### [F-004] High — Mid-flight lane change
**Impact:** Hot-reload can flip PAPER/URL between approve and submit.  
**Fix applied:** Lane snapshot + drift abort in `execute_trade`; refuse lane key changes while open signals exist; broker gate rechecks `LIVE_CAPITAL_DANGER`.

### [F-017] High — Wallet missing client_order_id
**Fix applied:** Stable `WALLET-…` client_order_id per plan line; `intent="manual"`.

### [F-018] High — Budget never accrues on Alpaca `success`
**Fix applied:** Accrue budget on `success`/`filled` for BUY opens (not closes).

### [F-019] Medium — Non-atomic settings/pairs JSON
**Fix applied:** temp + `fsync` + `os.replace`.

### [F-020] Medium — SQLite without WAL
**Status:** Open — recommend `PRAGMA journal_mode=WAL` + atomic budget increment.

### [F-021] Medium — KALMAN_DELTA ≥ 1 blows Q
**Fix applied:** `_guard_kalman_delta`; Kalman ctor raises; dashboard sensitive + clamp.

### [F-022] Medium — Risk knobs not step-up
**Fix applied:** Mark entry/TP/SL/drawdown/budget/ignore-unmanaged/kalman as sensitive (masked=False).

### [F-023] Medium — Pair universe without step-up
**Status:** Open (session-only `POST /api/pairs`).

### [F-024] Medium — 95% fill tolerance
**Status:** Open — Leg B should always size from actual Leg A fill (partially true today).

### [F-025] Medium — TOTP XOR with dashboard token
**Status:** Open — upgrade to Fernet + salted backup hashes.

### [F-026] Low — WS unbounded frames
**Status:** Open.

### [F-011] Medium — Docs vs login
**Status:** `frontend/README.md` already describes fail-closed login; no token-only claim found in current text.

### [F-006] High (prior) — Shadow SEC fail-open / data-source coint
**Status:** Design documented; no code change this phase.

### [F-012]/[F-013] Low
**Status:** F-013 covered by Phase-1 tests; F-012 legacy knobs remain.

---

## Success-criteria answers

| Question | Answer |
|---|---|
| Accidentally trade LIVE? | **Hard without** `PAPER_TRADING=false` + `LIVE_CAPITAL_DANGER` + human approve + broker gate. Telegram compromise still allows LIVE approve. |
| Risk limits bypassed? | **Capital halt** now on all broker opens; realized-PnL-only and F-015 races remain. |
| Duplicate trades? | **Mitigated** by `client_order_id`; concurrent approvals (F-015) still a gap. |
| Crash inconsistency? | **Improved** with pre-submit `ORDER_SUBMITTED`; Leg B window still thinner. |
| Approvals bypassed? | **Dashboard HTTP+terminal** require 2FA when enrolled; Telegram inline still chat-auth only. |
| Secrets leak? | Redaction present; TOTP storage (F-025) weaker than ideal. |
| Concurrency wrong positions? | **Possible** under F-015. |
| Broker/API unsafe? | Gate + budget + idempotency improved; wallet/MCP safer. |
| Phase-1 truly unbypassable? | **Not until Phase-2** for F-002/F-010; now mostly yes except Telegram/F-015. |

---

## Regression report

| Area | Result |
|---|---|
| Phase-1 tests | Still pass |
| Broker budget semantics | Intentionally changed (success accrues) — tests updated |
| Close paths | Explicit `intent="close"` so halt does not block exits |
| Dashboard risk knobs | Now require 2FA — tests updated |
| Performance | Negligible (extra halt DB read per open) |

---

## Coverage report

**Newly covered:** F-014 terminal 2FA path (API), broker gate halt/close/LIVE_CAPITAL, atomic JSON, Kalman delta, daily PnL fail-closed, pre-submit ledger assertions.  
**Gaps:** F-015 reservation, F-020 WAL, F-023 pairs 2FA, F-025 crypto, fault-injection crash mid-submit, concurrent approval stress.  
**Hard to test:** Real Alpaca reconnect races; Telegram callback compromise.

---

## Scores rationale

Security is not 9+ while Telegram can approve LIVE and TOTP is XOR-stored. Trading safety improved materially with a single broker submit gate. Reliability still missing WAL and open-slot reservation.
