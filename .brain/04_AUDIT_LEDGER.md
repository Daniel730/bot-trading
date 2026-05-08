# Audit Ledger

## Current Audition

The current audition is a workflow-safety audit, not a style or performance audit.

Primary question:

Can the bot move from signal to broker order to ledger state without creating duplicated orders, false fills, partial exposure, or silent unresolved state?

Active code areas under audition:

- `src/monitor.py`
- `src/services/brokerage/alpaca.py`
- `src/services/dashboard_service.py`
- `src/services/persistence_service.py`
- `tests/unit/test_monitor.py`
- `tests/unit/test_alpaca_provider.py`
- `tests/unit/test_dashboard_wallet_sync.py`
- `tests/unit/test_spread_guard_unit.py`
- `tests/unit/test_startup_guards.py`
- `infra/docker-compose.backend.yml`

## Dirty Worktree Snapshot At Brain Creation

`git diff --stat` showed:

- `infra/docker-compose.backend.yml`: 2-line security-sensitive change.
- `src/monitor.py`: large execution and recovery edits.
- `src/services/brokerage/alpaca.py`: ambiguous-submit reconciliation and stricter read failures.
- `src/services/dashboard_service.py`: paper-mode wallet sync behavior.
- `src/services/persistence_service.py`: fail-closed startup reconciliation.
- unit tests expanded around these areas.
- untracked `docs/prompts/` prompt set.

## Fresh Test Evidence

Command:

```bash
python -m pytest -q tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py
```

Result:

- 42 passed.
- 6 failed.

Failed tests:

| Test | Observed problem |
|---|---|
| `test_execute_trade_success` | Test did not mock fill polling correctly; execution tried to update real Postgres after unconfirmed fill path. |
| `test_execute_trade_emergency_closes_leg_a_when_leg_b_fails` | Test risk response lacks `max_allowed_fiat`, causing `KeyError`. |
| `test_close_position_skips_sell_when_broker_has_no_shares` | Failed in the active monitor close-workflow slice. Re-check exact assertion before fixing. |
| `test_execute_trade_crypto_live_uses_broker` | Failed in the active monitor live-execution slice. Re-check after adding fill polling mocks and full risk metadata. |
| `test_execute_trade_crypto_budget_cap_applied` | Test risk response lacks `max_allowed_fiat`, causing `KeyError`. |
| `test_orchestrator_veto` | Expected `VETOED`, but current profit guard returns `IGNORED` after net-profit veto. Decide expected precedence. |

Audit interpretation:

- The safety edits are incomplete until the monitor unit suite is green.
- Existing tests need to be updated to model the new contract: orders require fill snapshots and risk results include all fields the monitor logs/uses.
- Any code path that reaches real Postgres in a unit test probably lacks a persistence mock.

## 2026-05-08 Incremental Execution-Safety Audit Update

This update records targeted one-issue patches made after the initial brain snapshot. It does not mean the whole execution-safety slice is green; it means each listed invariant now has at least one focused regression test.

Fixed safety invariants:

| Area | Corrected assumption | Protecting test | Validation command |
|---|---|---|---|
| Successful pair entry reload | `LEG_A_FILLED` is not an open-position status. Both final legs of a fully opened pair must persist as `OPEN_PAIR`. | `tests/unit/test_monitor.py::test_execute_trade_success_marks_both_final_legs_open_pair` | `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_success_marks_both_final_legs_open_pair -q` |
| Leg B placement | A submitted/partial/rejected/zero-fill Leg A is not enough to place Leg B. Leg A must be confirmed full fill with positive quantity. | `tests/unit/test_monitor.py::test_execute_trade_blocks_leg_b_without_confirmed_leg_a_fill` | `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_blocks_leg_b_without_confirmed_leg_a_fill -q` |
| Alpaca submit timeout | Timeout after submit is not a normal failure and must not fallback-submit blindly. Reconcile by `client_order_id`; return `unknown` if unreconciled. | `tests/unit/test_alpaca_provider.py::test_place_value_order_timeout_reconciles_client_order_id_before_fallback`, `tests/unit/test_alpaca_provider.py::test_place_value_order_timeout_returns_unknown_when_reconcile_fails` | `.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q` |
| Monitor unknown submit handling | `status=unknown` / `requires_reconciliation` is neither success nor retryable failure. It blocks follow-up legs and records manual reconciliation. | `tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_leg_a_submission_ambiguous` | `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_leg_a_submission_ambiguous -q` |
| Close ledger state | Accepted close orders are not proof of closed exposure. Ledger closure requires confirmed filled close snapshots for all close orders. | `tests/unit/test_monitor.py::test_close_position_does_not_close_ledger_until_all_close_orders_fill` | `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_close_position_does_not_close_ledger_until_all_close_orders_fill -q` |
| Startup recovery | `CLOSING` rows after restart are unresolved state, not automatically reopenable positions. Startup must pause for manual reconciliation. | `tests/unit/test_startup_guards.py::test_startup_blocks_when_unresolved_execution_state_exists` | `.venv/bin/python -m pytest tests/unit/test_startup_guards.py::test_startup_blocks_when_unresolved_execution_state_exists -q` |
| Dashboard paper wallet | Paper mode must not place real broker wallet-sync orders. | `tests/unit/test_dashboard_wallet_sync.py` | `.venv/bin/python -m pytest tests/unit/test_dashboard_wallet_sync.py -q` |
| Spread guard | Missing, non-numeric, zero, or invalid bid/ask is not acceptable market data. Reject before risk and broker paths. | `tests/unit/test_spread_guard_unit.py::test_spread_guard_rejects_missing_bid_ask` | `.venv/bin/python -m pytest tests/unit/test_spread_guard_unit.py::test_spread_guard_rejects_missing_bid_ask -q` |
| Pending-order budget read | Failed pending-order value read is unknown exposure, not zero pending exposure. Block entry before risk/order. | `tests/unit/test_monitor.py::test_execute_trade_blocks_when_pending_orders_budget_read_fails` | `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_blocks_when_pending_orders_budget_read_fails -q` |
| Alpaca open-order read | Failed `list_orders(status='open')` is not an empty open-order book. | `tests/unit/test_alpaca_provider.py::test_alpaca_pending_orders_raise_on_fetch_failure` | `.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q` |
| Fill confirmation | Absence from open orders is not proof of fill when no order snapshot confirms terminal state. | `tests/unit/test_monitor.py::test_await_order_fill_does_not_assume_missing_open_order_is_filled` | `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_await_order_fill_does_not_assume_missing_open_order_is_filled -q` |
| Alpaca order snapshot read | Failed `get_order()` is not an empty order snapshot. | `tests/unit/test_alpaca_provider.py::test_alpaca_get_order_raises_on_fetch_failure` | `.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q` |
| Alpaca position read | Failed `get_position(ticker)` is not zero shares. Only real not-found position returns `[]`. | `tests/unit/test_alpaca_provider.py::test_alpaca_get_positions_for_ticker_raises_on_read_failure` | `.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q` |
| Alpaca portfolio read | Failed portfolio read is not an empty portfolio. | `tests/unit/test_alpaca_provider.py::test_alpaca_get_portfolio_raises_on_read_failure` | `.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q` |
| Emergency close ambiguity | Emergency close `unknown` is not success. Persist orphan/manual reconciliation state. | `tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous` | `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous -q` |

Observed validation notes:

- `tests/unit/test_alpaca_provider.py -q` passed after provider read-failure patches.
- Focused monitor tests for successful entry and emergency close ambiguity passed, but are slow in the current environment.
- `tests/unit/test_monitor.py::test_close_position_skips_sell_when_broker_has_no_shares` still attempted a real Postgres connection and failed on DNS/name resolution during one run; this is a test isolation problem to fix before claiming the monitor suite is green.
- `git diff --check -- src/monitor.py tests/unit/test_monitor.py` and targeted provider/dashboard files passed; full `git diff --check` still reports pre-existing trailing whitespace in `infra/docker-compose.backend.yml`.

## Previous Readiness Evidence From Docs

From `docs/production-scan-report.md`:

- Docker services were up: bot, frontend, execution-engine, mcp-server, postgres, redis, sec-worker.
- `python scripts/validate_deploy_env.py .env` passed.
- Focused startup/safety/budget tests passed: 14 passed.
- Multi-profile integration simulation passed: 10 passed.
- Verdict remained not fully ready for production because prior logs showed Postgres auth instability and gRPC transport noise.

From `docs/soak-fault-injection-report.md`:

- Controlled restarts of Redis, Postgres, and execution-engine recovered to healthy.
- Post-recovery logs showed bot loop heartbeat and repeated API 200s.
- Post-drill focused tests had 2 passed.
- Extended post-recovery smoke had 1 failed, 4 passed.
- Remaining failure: `test_terminal_command_integration`, caused by missing `session_token` in an auth/login response expectation.
- Production approval remained not approved.

## Historical Audit Artifacts

Use current source and current tests first, but keep these as context:

- `docs/tofix.md`: preferred current short backlog as of 2026-04-30.
- `docs/needs-to-analyse.md`: next analysis matrix.
- `docs/production-readiness-plan.md`: production gate and soak plan.
- `docs/production-scan-report.md`: readiness scan evidence.
- `docs/soak-fault-injection-report.md`: restart drill evidence.
- `docs/bugs.md`: older full bug register, not the current backlog.
- `docs/MONDAY_READINESS_AUDIT.md`: historical paper-trading readiness state for 2026-04-20.
- `.gemini/mvp_analysis.md`: older MVP diagnosis, partly superseded but still useful for context.

## Current Audit Questions

1. Does `_await_order_fill()` handle provider read failures without assuming success?
2. Does every order submission carry a stable client order ID?
3. Does an ambiguous Alpaca submit avoid fallback resubmission?
4. Does leg B only submit after leg A is confirmed filled?
5. Does an unknown leg B or emergency close state block automation and notify the operator?
6. Does startup block when unresolved ledger rows exist?
7. Does paper-mode dashboard wallet sync avoid broker calls?
8. Does the test suite express the new fail-closed contract?
9. Does Compose still require explicit non-default PostgreSQL credentials?
10. Does documentation match the current Alpaca-only brokerage facade?
