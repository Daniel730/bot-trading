# DECISIONS.md

Runtime and safety decisions recorded during the 2026-08-04 full-day audit and Phase-2 remediation.

## Execution lanes

- **SHADOW** (`PAPER_TRADING=true`): simulated fills only; broker opens refused at `BrokerageService._pre_submit_gate`.
- **BROKER_PAPER** (`PAPER_TRADING=false` + hostname `paper-api.alpaca.markets` + `LIVE_CAPITAL_DANGER=true`): real paper orders; auto-approve allowed.
- **LIVE** (real Alpaca host): never auto-approve via notional threshold; human approve required.

## Approval

- `APPROVAL_THRESHOLD` is **not** an auto-approve switch for LIVE (F-001).
- Dashboard approve/reject **and** terminal `/approve|/reject|/set_threshold` require step-up 2FA when enrolled (F-010/F-014).
- Telegram inline buttons remain chat-id authenticated (accepted residual threat model until chat-binding hardening).

## Capital halt (F-002)

- New opens blocked when operational pause / daily realized loss ≥ `MAX_DRAWDOWN` / rolling max drawdown ≥ limit.
- Enforced in `Monitor.execute_trade` **and** `BrokerageService.place_*` for `intent in {open, manual}`.
- Closes use `intent="close"` and are never blocked by capital halt.
- Broker/live: daily PnL read failure → fail-closed halt. Shadow: soft-fail to 0.

## Broker submit gate (F-004)

- Every non-close submit rechecks `LIVE_CAPITAL_DANGER` and capital halt.
- `execute_trade` snapshots lane knobs and aborts on mid-flight drift.
- Dashboard refuses PAPER/URL/DEV/LIVE_CAPITAL flips while open signals exist.

## Crash recovery (F-007/F-016)

- Persist `ORDER_SUBMITTED` with `client_order_id` before Leg A place; promote with `attach_broker_order_id`.
- Startup unresolved set already includes `ORDER_SUBMITTED`.

## Persistence

- `bot_settings.json` / `pairs.json` written atomically (temp + fsync + replace) (F-019).
- SQLite WAL still pending (F-020).

## Budget (F-018)

- Accrue used budget on Alpaca `success` or `filled` for BUY opens (not closes).

## Kalman (F-021)

- `KALMAN_DELTA` must be in `(0, 1)` exclusive; validated in Settings + Kalman ctor.
