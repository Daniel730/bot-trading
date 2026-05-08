# Do Not Do

## Live Capital

- Do not run live capital just because unit tests pass.
- Do not set Java `DRY_RUN=false`.
- Do not rely on `DEV_MODE=true` for production behavior.
- Do not allow live approvals without Telegram unless explicitly testing that fallback.
- Do not use a branch with unresolved execution-state test failures for live trading.

## Broker And Orders

- Do not treat a network timeout as order rejection.
- Do not treat absence from open orders as proof of fill.
- Do not submit leg B unless leg A is confirmed fully filled.
- Do not resubmit after an ambiguous submit unless a reconciled broker state proves it is safe.
- Do not close the ledger based only on close order submission.
- Do not reopen `CLOSING` rows as `OPEN` during startup recovery.
- Do not discard `client_order_id`; it is the reconciliation handle.
- Do not use requested quantity/price as final fill truth when broker fill data exists.

## Secrets And Config

- Do not commit real `.env` secrets.
- Do not add default dashboard tokens or database passwords.
- Do not loosen `POSTGRES_PASSWORD` or `DASHBOARD_TOKEN` validation.
- Do not expose dashboard or FastMCP ports publicly without reviewing auth.
- Do not make wildcard CORS valid outside `DEV_MODE=true`.

## Tests

- Do not call real Postgres from unit tests.
- Do not let tests sleep through 30-second polling loops unless the timeout itself is under test.
- Do not patch around failures by deleting safety assertions.
- Do not update expected results to optimistic behavior without proving broker state.
- Do not use old audit docs as proof that current code is safe.

## Architecture

- Do not assume T212/Web3 are active live paths in current code.
- Do not broaden brokerage routing before Alpaca fail-closed behavior is green.
- Do not refactor wide architecture during a bug audit unless the bug requires it.
- Do not optimize performance before order-state correctness.
- Do not move legacy providers back into active routing without fake-provider contract tests.

## Documentation

- Do not let README/docs imply production readiness while `10_RELEASE_CHECKLIST.md` blocks it.
- Do not leave `.brain/` stale after changing execution, startup, broker, auth, or release posture.
- Do not copy historical bug lists into current state without revalidating them against current code.
