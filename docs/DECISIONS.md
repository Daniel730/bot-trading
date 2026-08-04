# DECISIONS.md

Runtime and safety decisions recorded during the 2026-08-04 full-day audit and Phase-2/3 remediations.

## Execution lanes

- **SHADOW** (`PAPER_TRADING=true`): simulated fills only; broker opens refused at `BrokerageService._pre_submit_gate`.
- **BROKER_PAPER** (`PAPER_TRADING=false` + hostname `paper-api.alpaca.markets` + `LIVE_CAPITAL_DANGER=true`): real paper orders; auto-approve allowed.
- **LIVE** (real Alpaca host): never auto-approve via notional threshold; human approve required via dashboard + step-up 2FA.

## Approval

- `APPROVAL_THRESHOLD` is **not** an auto-approve switch for LIVE (F-001).
- Dashboard approve/reject **and** terminal `/approve|/reject|/set_threshold` require step-up 2FA when enrolled (F-010/F-014).
- **Phase-3:** LIVE Telegram **trade** Approve is refused (`pending_approval_summaries`); dashboard + 2FA is mandatory. Login Approve via Telegram remains allowed. LIVE `/invest` and LIVE DCA schedule via Telegram are refused.
- Paper / Alpaca-paper auto-approve (`should_auto_approve_trades`) unchanged.

## Open-slot reservation (F-015)

- Claim pair/leg slot **before** `request_approval`; hold through `execute_trade`; release in `finally`.
- Durable append-only checksummed WAL; replay on startup (fail-closed holds until TTL/RELEASE).
- Process-local lock only — multi-host LIVE requires shared lock (documented residual R-301).

## Capital halt (F-002)

- New opens blocked when operational pause / daily realized loss ≥ `MAX_DRAWDOWN` / rolling max drawdown ≥ limit.
- Enforced in `Monitor.execute_trade` **and** `BrokerageService.place_*` for `intent in {open, manual}`.
- Closes use `intent="close"` and are never blocked by capital halt.
- Broker/live: daily PnL read failure → fail-closed halt. Shadow: soft-fail to 0.

## Broker submit gate (F-004)

- Every non-close submit rechecks `LIVE_CAPITAL_DANGER` and capital halt.
- `execute_trade` snapshots lane knobs and aborts on mid-flight drift.
- Dashboard refuses PAPER/URL/DEV/LIVE_CAPITAL flips while open signals exist.

## Crash recovery (F-007/F-016 / F-020)

- Persist `ORDER_SUBMITTED` with `client_order_id` before Leg A place; promote with `attach_broker_order_id`.
- Startup unresolved set already includes `ORDER_SUBMITTED`.
- SQLite `PRAGMA journal_mode=WAL` + `BEGIN IMMEDIATE` system_state / atomic budget increment.
- Trade-intent WAL for open-slot CLAIM/RELEASE.

## Persistence

- `bot_settings.json` / `pairs.json` written atomically (temp + fsync + replace) (F-019).
- Intent WAL: append-only JSONL, per-record SHA-256, fsync (F-015/F-020).

## Budget (F-018)

- Accrue used budget on Alpaca `success` or `filled` for BUY opens (not closes).
- Accrue via `increment_system_state_float` (F-020).

## Config / authz (F-022 / F-023 / F-025)

- Risk knobs sensitive (masked=False) with step-up.
- Pair universe mutate + discover require step-up when 2FA enrolled (F-023).
- TOTP secrets Fernet-encrypted; backup codes salted HMAC; legacy XOR/SHA migrate (F-025). Prefer `TOTP_ENCRYPTION_KEY`.

## Kalman (F-021)

- `KALMAN_DELTA` must be in `(0, 1)` exclusive; validated in Settings + Kalman ctor.

## Production posture (Phase-3)

- Verdict: **READY FOR PAPER TRADING ONLY** (see `docs/AUDIT_PHASE3.md`).
- LIVE capital remains blocked by multi-process reservation gap, Leg B orphans, unrealized drawdown design.
