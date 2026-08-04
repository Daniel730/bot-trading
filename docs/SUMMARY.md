# SUMMARY.md

## What shipped (2026-08-04)

1. **Full-day local SHADOW soak** + harness (`scripts/full_day_audit_*`, longwatch).
2. **Phase-1 adversarial audit** (`docs/AUDIT_TECHNICAL_2026-08-04.md`) and remediations F-001…F-010 (subset).
3. **Phase-2 independent audit** (`docs/AUDIT_PHASE2.md`) proving path gaps and closing them.

## Phase-2 remediations (high level)

- Terminal approve/reject/threshold → step-up 2FA (F-014).
- Capital halt + LIVE_CAPITAL assert on all broker opens (F-002/F-004).
- Pre-submit `ORDER_SUBMITTED` ledger + attach broker id (F-007/F-016).
- Lane snapshot / block mode flip with open book (F-004).
- Wallet `client_order_id` (F-017); budget on `success` (F-018).
- Atomic JSON overrides (F-019); Kalman delta clamp (F-021); risk knobs sensitive (F-022).

## Still open

- Concurrent approval reservation (F-015).
- SQLite WAL (F-020); pairs API step-up (F-023); TOTP crypto (F-025).
- Telegram approve without 2FA (design residual).

## Verification

- Backend unit: **790 passed** (excl. flaky MAB).
- Frontend: **166** vitest + eslint clean.
- PR: https://github.com/Daniel730/bot-trading/pull/116
