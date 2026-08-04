# DECISIONS.md

Runtime and safety decisions recorded during the 2026-08-04 full-day audit and Phase-2/3/4 remediations.

## Execution lanes

- **SHADOW** (`PAPER_TRADING=true`): simulated fills only; broker opens refused at `BrokerageService._pre_submit_gate`.
- **BROKER_PAPER** (`PAPER_TRADING=false` + hostname `paper-api.alpaca.markets` + `LIVE_CAPITAL_DANGER=true`): real paper orders; auto-approve allowed.
- **LIVE** (real Alpaca host): never auto-approve via notional threshold; human approve via dashboard + step-up 2FA; **LIVE readiness checklist must pass**.

## Approval

- `APPROVAL_THRESHOLD` is **not** an auto-approve switch for LIVE (F-001).
- Dashboard approve/reject **and** terminal `/approve|/reject|/set_threshold` require step-up 2FA when enrolled (F-010/F-014).
- LIVE Telegram **trade** Approve is refused; login Approve remains allowed. LIVE `/invest` and LIVE DCA schedule via Telegram are refused.
- Paper / Alpaca-paper auto-approve (`should_auto_approve_trades`) unchanged.

## Distributed reservation (R-301 / Phase-4)

- Authority is **PostgreSQL**: `pg_advisory_xact_lock` + partial unique indexes on active legs/pair + `signal_id` PK.
- File WAL is an append-only **audit mirror**, not the lock.
- Python/asyncio locks are cache-only — never the safety boundary.
- Fail-closed if distributed store unavailable.

## Exactly-once (Phase-4)

- `execution_intents` unique on `(signal_id, leg)` and `client_order_id`.
- Intent row required before Leg A / Leg B broker submit.

## Open-slot reservation (F-015)

- Claim pair/leg slot **before** `request_approval`; hold through `execute_trade`; release in `finally`.
- Phase-4: claims go through distributed Postgres store.

## Capital halt (F-002 / R-303)

- New opens blocked on operational pause / daily realized loss / rolling max drawdown / **equity HWM drawdown**.
- Enforced in `Monitor.execute_trade` **and** `BrokerageService.place_*` for `intent in {open, manual}`.
- Closes use `intent="close"` and are never blocked by capital halt.
- Broker/live: PnL or equity read failure → fail-closed halt. Shadow: soft-fail where appropriate.

## Broker as source of truth (Phase-4)

- Continuous reconciliation loop (default 60s) + startup cycle.
- Order: confirmed closes → pair restores → flat orphans → Leg-A orphan flatten → plan audit.
- Local ledger is never absolute truth.

## Leg orphan recovery (R-302)

- Automatic emergency close when Leg A exists at broker without Leg B.
- `LEG_A_FILLED` included in startup unresolved statuses.

## LIVE readiness (Phase-4)

- Checklist must pass before LIVE opens: broker, WAL, DB, no pending intents, no orphans, drawdown/capital, 2FA, config, clock, secrets, fresh reconcile.
- Paper / auto-approve lanes skip the checklist.

## Broker submit gate (F-004)

- Every non-close submit rechecks `LIVE_CAPITAL_DANGER` and capital halt.
- `execute_trade` snapshots lane knobs and aborts on mid-flight drift.
- Dashboard refuses PAPER/URL/DEV/LIVE_CAPITAL flips while open signals exist.

## Crash recovery (F-007/F-016 / F-020)

- Persist `ORDER_SUBMITTED` with `client_order_id` before Leg A place; promote with `attach_broker_order_id`.
- SQLite `PRAGMA journal_mode=WAL` + atomic budget increment (local SQLite paths).
- Intent WAL + Postgres reservations for multi-instance.

## Persistence

- `bot_settings.json` / `pairs.json` written atomically (temp + fsync + replace) (F-019).
- Intent WAL: append-only JSONL, per-record SHA-256, fsync.

## Budget (F-018)

- Accrue used budget on Alpaca `success` or `filled` for BUY opens (not closes).
- Accrue via `increment_system_state_float` (F-020).

## Config / authz (F-022 / F-023 / F-025)

- Risk knobs sensitive with step-up.
- Pair universe mutate + discover require step-up when 2FA enrolled (F-023).
- TOTP secrets Fernet-encrypted; backup codes salted HMAC; legacy XOR/SHA migrate (F-025).

## Kalman (F-021)

- `KALMAN_DELTA` must be in `(0, 1)` exclusive.

## Production posture

- Phase-3: paper-ready.
- Phase-4 verdict: **READY FOR LIMITED LIVE CAPITAL** — small capital, checklist-gated.
- Phase-5 ops: provenance, replay, Decision Package, severity-based divergence, limited-LIVE kill.
- **Dual-track roadmap** (`docs/ROADMAP_DUAL_TRACK.md`): platform = maintenance; research = primary effort.
- Strategy Acceptance Protocol gates LIVE eligibility (`research/STRATEGY_ACCEPTANCE_PROTOCOL.md`).
- Platform maturity ≠ statistical edge.
