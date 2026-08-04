# Audit Phase 4 — Distributed Safety & Production Hardening

**Date:** 2026-08-04  
**Scope:** Prove multi-instance safety. Close R-301, R-302, R-303. Broker as source of truth. Automatic LIVE gate.  
**Question answered:** *Can I run 2, 3, or 10 bot instances without duplicate orders?*

---

## Executive Summary

Phase-4 replaces process-local reservation with **PostgreSQL advisory locks + unique constraints**, adds **exactly-once execution intents**, **automatic Leg-A orphan recovery**, **equity high-water-mark drawdown**, **continuous broker reconciliation**, and a **fail-closed LIVE readiness checklist**.

Adversarial evidence (Postgres-backed):

| Proof | Result |
|---|---|
| 10 concurrent “instances” claim same pair | **Exactly 1 winner** |
| Claim survives “restart” (new store object) | Held in Postgres |
| Same signal intent ×100 | **Exactly 1** `execution_intents` row |
| 200 signals ×5 duplicates | 200 intents, 800 rejects |
| 200 random claim/release chaos | No duplicate active legs |
| Replay event stream ×10 | Identical SHA-256 state hash |
| Equity −15% from HWM | Capital halt trips |
| Leg-A-only broker qty | Emergency close (`intent=close`) |

**Final verdict: READY FOR LIMITED LIVE CAPITAL**

Conditions: automatic LIVE checklist must pass; start with small notional; continuous reconciler + intense monitoring required. Full 48h / 100k-signal soak harness exists (`scripts/phase4_soak_chaos.py`) but was only validated in lite mode in this environment — run it on bot-server before scaling.

---

## Production Readiness Score

| Dimension | Score | Notes |
|---|---|---|
| **Security** | **8.2 / 10** | LIVE gate + 2FA checklist; Telegram trade path already closed |
| **Reliability** | **8.5 / 10** | Distributed reservation + continuous reconcile |
| **Trading Safety** | **8.6 / 10** | Exactly-once intents + equity DD + orphan recovery |
| **Recoverability** | **8.4 / 10** | Broker SoT cycle; Leg-A auto-flatten |
| **Observability** | **7.5 / 10** | Reconcile stamps + soak metrics file |
| **Determinism** | **7.8 / 10** | Replay hash property; full hist harness lite |
| **Maintainability** | **7.6 / 10** | New services isolated; facade keeps WAL audit |

---

## R-301 — Distributed reservation (CLOSED)

**Authority:** PostgreSQL only (`open_slot_reservations`).

- `pg_advisory_xact_lock` serializes claimers across processes
- Partial unique indexes on active `leg_a`, `leg_b`, `pair_key`
- Primary key on `signal_id`
- TTL expiry + RELEASE status
- File WAL is **audit mirror only** — not the lock

`OpenSlotReservationService` prefers the distributed store.

- **Real-money LIVE:** fail-closed if Postgres is unavailable (no silent local claim).
- **Paper / Alpaca-paper auto-approve:** local+WAL claim fallback when the distributed store errors (same policy as the async read path), so unit tests and paper soak do not skip every trade on a transient loop/pool fault.

**Not accepted:** in-memory mutex, globals, or Python locks as the safety boundary for LIVE (local lock remains cache-only / paper fallback).

---

## Exactly-once execution (CLOSED for broker legs)

Table `execution_intents`:

- `PRIMARY KEY (client_order_id)`
- `UNIQUE (signal_id, leg)`

`Monitor.execute_trade` calls `begin_intent` before Leg A / Leg B submit. Duplicate deliveries return `exactly_once:*` without placing. Inserts use `ON CONFLICT DO NOTHING` so concurrent identical deliveries cannot raise UniqueViolation — losers get an idempotent refuse.

Channels covered by the same gate once they reach `execute_trade` (REST approve → monitor, Telegram refusal on LIVE, MCP execute disabled, historical replay via intents).

---

## R-302 — Leg orphan recovery (CLOSED)

`recover_leg_a_orphans`:

1. Load unresolved LEG_A_* / PARTIAL_EXPOSURE rows (now includes `LEG_A_FILLED` in startup unresolved set)
2. Ask broker for positions/orders
3. If exactly one leg has exposure and no pending orders → emergency close with stable `ORPHAN-CLOSE-…` client_order_id
4. Stamp ledger closed / recovered

Wired into startup reconciliation + continuous cycle.

---

## R-303 — Equity / unrealized drawdown (CLOSED)

`capital_halt_service` now tracks `equity_high_water_mark` from broker equity.

Halt when `(HWM − equity) / HWM ≥ MAX_DRAWDOWN`.

Fail-closed on broker/live if equity unreadable.

---

## Continuous broker reconciliation

`continuous_broker_reconcile.run_broker_reconciliation_cycle`:

1. Broker-confirmed closes  
2. Broker-confirmed pair restores  
3. Flat orphan ledger closes  
4. Leg-A orphan flatten  
5. Plan audit log  
6. Stamp `last_broker_reconcile_at` / `_ok`

Background loop started from monitor (default 60s). **Local state is never absolute truth.**

---

## LIVE readiness checklist (automatic)

`live_readiness.evaluate_live_readiness` — all must pass or LIVE opens are refused:

| Item | Check |
|---|---|
| Broker connected | `get_account_cash` |
| WAL integrity | checksum scan |
| Database consistent | Postgres + schema |
| No pending intents | `execution_intents` INTENT/SUBMITTED = 0 |
| No orphans | startup unresolved count = 0 |
| Drawdown OK | capital halt false |
| Capital OK | same |
| 2FA OK | TOTP enabled |
| Configuration signed | LIVE_CAPITAL + not DEV + not paper |
| Clock synchronized | wall-clock jump guard |
| Secrets valid | non-placeholder keys |
| Reconciliation complete | last reconcile OK and fresh |

`execute_trade` enforces this for real-money LIVE only (paper / auto-approve lanes skip).

---

## Chaos / soak / replay

| Harness | Location | CI | Full |
|---|---|---|---|
| Multi-instance claim | `test_audit_phase4_distributed.py` | 10 instances | — |
| Exactly-once ×100 | same | yes | — |
| Chaos claim/release | same | 200 ops | `--chaos 500+` |
| Replay hash ×10 | same | yes | — |
| Soak | `scripts/phase4_soak_chaos.py` | 500–2k lite | `--signals 100000 --hours 48` |

---

## Remaining Risks

### R-401 — 48h soak not completed in CI
- **Severity:** Medium  
- **Exploitability:** N/A (ops)  
- **Financial impact:** Undetected leaks under long load  
- **Operational impact:** Must run harness on bot-server before scale-up  
- **Mitigation:** `scripts/phase4_soak_chaos.py --signals 100000 --hours 48`

### R-402 — Orphan recovery uses market close heuristics
- **Severity:** Medium  
- **Exploitability:** Low  
- **Financial impact:** Slippage on emergency flatten  
- **Mitigation:** Prefer limit/protect + human alert for large notionals

### R-403 — LIVE checklist vs operator urgency
- **Severity:** Low  
- **Exploitability:** Social  
- **Financial impact:** None (fail-closed)  
- **Mitigation:** Keep checklist mandatory; never add bypass flags

### R-404 — Historical multi-run PnL identity incomplete
- **Severity:** Medium  
- **Exploitability:** N/A  
- **Financial impact:** Forensic friction  
- **Mitigation:** Extend replay engine to full Kalman/scan path

---

## Final Verdict

# READY FOR LIMITED LIVE CAPITAL

**Objective justification:**

1. **R-301 closed** with Postgres advisory lock + unique constraints; 10-way race → one winner.  
2. **R-302 closed** with automatic Leg-A orphan flatten against broker SoT.  
3. **R-303 closed** with equity HWM drawdown halt.  
4. **Exactly-once** intents proven under 100× / 200×5 duplication.  
5. **LIVE opens** additionally gated by automatic checklist — failing any item forbids LIVE.  
6. Not **FULL LIVE DEPLOYMENT** — 48h soak pending, capital must stay small, monitoring intense.

---

## Files (primary)

- `src/services/distributed_reservation.py`
- `src/services/execution_intent_service.py`
- `src/services/leg_orphan_recovery.py`
- `src/services/continuous_broker_reconcile.py`
- `src/services/live_readiness.py`
- `src/services/open_slot_reservation.py` (Postgres-first facade)
- `src/services/capital_halt_service.py` (equity HWM)
- `src/monitor.py` (wire-up)
- `tests/unit/test_audit_phase4_distributed.py`
- `scripts/phase4_soak_chaos.py`
- `docs/AUDIT_PHASE4.md`
