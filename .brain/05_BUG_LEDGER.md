# Bug Ledger

## 2026-05-08 Closed / Protected Execution-Safety Bugs

These are closed only for the specific invariant named. Do not generalize them into production readiness.

### CLOSED: Successful entries must reload as two-leg open positions

- Fixed: final successful Leg A rows now persist as `OPEN_PAIR` when the pair is fully open.
- Corrected assumption: a leg-level filled status is not equivalent to an open-position status.
- Protecting test: `tests/unit/test_monitor.py::test_execute_trade_success_marks_both_final_legs_open_pair`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_success_marks_both_final_legs_open_pair -q`.

### CLOSED: Leg B placement after ambiguous Leg A

- Fixed: Leg B is blocked unless Leg A is confirmed `filled` with positive `filled_qty`.
- Corrected assumption: submitted, partial, rejected, canceled, expired, zero-fill, or unknown Leg A is not safe enough to hedge with Leg B.
- Protecting test: `tests/unit/test_monitor.py::test_execute_trade_blocks_leg_b_without_confirmed_leg_a_fill`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_blocks_leg_b_without_confirmed_leg_a_fill -q`.

### CLOSED: Alpaca submit timeout fallback duplicate-risk

- Fixed: ambiguous Alpaca submit exceptions reconcile by `client_order_id`; unreconciled submit returns `status=unknown` / `requires_reconciliation=true` and does not fallback-submit.
- Corrected assumption: timeout after submit is not proof of broker rejection.
- Protecting tests: `test_place_value_order_timeout_reconciles_client_order_id_before_fallback`, `test_place_value_order_timeout_returns_unknown_when_reconcile_fails`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q`.

### CLOSED: Monitor follow-up after unknown submit

- Fixed: unknown Leg A/Leg B submit state records manual reconciliation and blocks follow-up automation.
- Corrected assumption: unknown submit state is neither success nor retryable failure.
- Protecting test: `tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_leg_a_submission_ambiguous`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_leg_a_submission_ambiguous -q`.

### CLOSED: Ledger close before confirmed close fills

- Fixed: live close path waits for confirmed fill snapshots and keeps ledger open/manual-reconciliation on unknown or unfilled close state.
- Corrected assumption: accepted close orders are not proof of closed exposure.
- Protecting tests: `test_close_position_success`, `test_close_position_does_not_close_ledger_until_all_close_orders_fill`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_close_position_success tests/unit/test_monitor.py::test_close_position_does_not_close_ledger_until_all_close_orders_fill -q`.

### CLOSED: Startup blind reopen of `CLOSING`

- Fixed: startup marks unsafe unresolved rows for manual reconciliation and pauses scanning.
- Corrected assumption: `CLOSING` after restart is not safely reopenable without broker reconciliation.
- Protecting test: `tests/unit/test_startup_guards.py::test_startup_blocks_when_unresolved_execution_state_exists`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_startup_guards.py::test_startup_blocks_when_unresolved_execution_state_exists -q`.

### CLOSED: Paper-mode dashboard wallet broker calls

- Fixed: dashboard wallet buy/sync returns paper order records and avoids broker order placement when `PAPER_TRADING=true`.
- Corrected assumption: dashboard wallet actions are not exempt from paper/live mode separation.
- Protecting tests: `tests/unit/test_dashboard_wallet_sync.py`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_dashboard_wallet_sync.py -q`.

### CLOSED: Missing bid/ask spread guard fail-open

- Fixed: missing, non-numeric, zero, or invalid bid/ask rejects before risk sizing and broker order creation.
- Corrected assumption: absence of bid/ask is not a warning-only condition.
- Protecting test: `tests/unit/test_spread_guard_unit.py::test_spread_guard_rejects_missing_bid_ask`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_spread_guard_unit.py::test_spread_guard_rejects_missing_bid_ask -q`.

### CLOSED: Pending-order read failure as zero pending exposure

- Fixed: monitor blocks entry if pending-order value cannot be read.
- Corrected assumption: failed pending-order read is unknown exposure, not `0.0`.
- Protecting test: `tests/unit/test_monitor.py::test_execute_trade_blocks_when_pending_orders_budget_read_fails`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_blocks_when_pending_orders_budget_read_fails -q`.

### CLOSED: Alpaca broker reads returning safe-looking empty state

- Fixed: Alpaca `get_pending_orders()`, `get_order()`, `get_positions(ticker)`, and `get_portfolio()` now raise on read failures. `get_positions(ticker)` still returns `[]` for real not-held/not-found positions.
- Corrected assumption: broker read failure is not the same as empty orders, empty snapshots, zero shares, or empty portfolio.
- Protecting tests: `test_alpaca_pending_orders_raise_on_fetch_failure`, `test_alpaca_get_order_raises_on_fetch_failure`, `test_alpaca_get_positions_for_ticker_raises_on_read_failure`, `test_alpaca_get_portfolio_raises_on_read_failure`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q`.

### CLOSED: Emergency close unknown treated as success

- Fixed: emergency close `unknown` / `requires_reconciliation` now logs and persists orphan/manual-reconciliation state instead of claiming success.
- Corrected assumption: emergency close submit ambiguity is not close success.
- Protecting test: `tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous -q`.

## P0: Must Resolve Before Any Production Sign-Off

### P0-001: Hardcoded PostgreSQL fallback in backend compose

- Location: `infra/docker-compose.backend.yml`
- State at brain creation: dirty worktree changed `POSTGRES_PASSWORD` from required to a concrete fallback value.
- Risk: containers can boot with a known/default database secret, directly contradicting `config.py`, `.env.template`, and docs.
- Required fix: restore required secret behavior or another no-default mechanism. Do not ship a real password in Compose.

### P0-002: Focused execution-safety test slice is not green

- Evidence: 42 passed, 6 failed on 2026-05-07.
- Risk: current active fail-closed edits are not yet proven.
- Current update: many focused tests now pass, but the full focused monitor/provider slice still needs a clean rerun.
- Known test-isolation issue: `tests/unit/test_monitor.py::test_close_position_skips_sell_when_broker_has_no_shares` reached real Postgres during a targeted run and failed on DNS/name resolution.
- Required fix: update tests and/or code so the new order-fill/reconciliation contract is explicit and green, with no unit test touching real Postgres.

### P0-003: Production remains not approved

- Evidence: `docs/production-scan-report.md` and `docs/soak-fault-injection-report.md`.
- Risk: functional tests and restart drills are encouraging, but not enough for live capital.
- Required fix: longer soak, clean logs, full smoke, active scan cycle, and release checklist.

### P0-004: Unresolved execution state must block startup

- Current code direction: `_fail_fast_on_unresolved_execution_state()` blocks when ambiguous rows exist.
- Risk if regressed: duplicate close orders, reopened exposure, or ledger/broker divergence after crash.
- Required test: startup with `CLOSING`, `NEEDS_MANUAL_RECONCILIATION`, or `FAILED_REQUIRES_MANUAL_RECONCILIATION` rows must pause.

## P1: High Financial Or Workflow Risk

### P1-001: Alpaca ambiguous submit handling is under active audition

- Location: `src/services/brokerage/alpaca.py`, `src/monitor.py`.
- Current direction: reconcile by `client_order_id`; return `unknown` if not reconciled; monitor must not resubmit blindly.
- Risk: timeouts after broker accept can otherwise duplicate orders.
- Required proof: tests for timeout reconciled, timeout unreconciled, no fallback submit, monitor manual reconciliation.

### P1-002: Partial fills are still not fully end-to-end modeled

- Current direction: monitor blocks leg B unless leg A is fully confirmed.
- Remaining risk: fill quantity, average fill price, remaining quantity, fees, and broker status polling need consistent persistence across entry and close.
- Required proof: contract tests with fake Alpaca provider for partial fill, zero-fill `filled`, canceled, expired, rejected, and stale order snapshot.

### P1-003: Close workflow can create ledger/broker divergence if not fully confirmed

- Current direction: require close fill snapshots before ledger closure.
- Risk: a close submit can be accepted but the process can crash before ledger update.
- Current update: ledger closure now requires close-fill confirmation; unknown close states update manual reconciliation.
- Still open: emergency-close success after Leg B rejection is not yet fill-confirmed; accepted emergency close is still not proof of flat exposure.
- Required proof: tests for emergency close success accepted-but-unfilled, one close fill confirmed then second close unknown/fails, and startup requiring manual reconciliation.

### P1-007: Account balance reads still return `0.0` on broker failure

- Location: `src/services/brokerage/alpaca.py`.
- Current behavior: `get_account_cash()`, `get_account_equity()`, and `get_account_buying_power()` log and return `0.0` on read failure.
- Risk: unavailable account state can look like depleted funds; this may block entries for the wrong reason and can corrupt dashboards/budget diagnostics.
- Required fix: raise on account read failure and make live execution fail closed with an operator-visible message.
- Required tests: provider tests for each account read raising on API failure; monitor test that live execution blocks before risk/order when account reads fail.

### P1-008: Emergency close success still needs fill confirmation

- Location: `src/monitor.py`, Leg B rejection emergency close branch.
- Current behavior: emergency close `unknown` is now manual reconciliation, but a `success` submit still logs emergency close success without polling for actual fill.
- Risk: Leg A directional exposure can remain open while logs imply it was closed.
- Required fix: after emergency close submit success, reconcile/poll fill before claiming flat; if unconfirmed, persist manual reconciliation.
- Required test: Leg A filled, Leg B rejected, emergency close submit success but fill polling returns `None` or non-filled; expect `FAILED_REQUIRES_MANUAL_RECONCILIATION`.

### P1-004: Documentation and implementation disagree on live venues

- Docs: Trading 212, Alpaca, Web3 are described as active live routing options.
- Current code: `BrokerageService` forces Alpaca; legacy providers moved to `legacy/`; `settings.BROKERAGE_PROVIDER` is forced to `ALPACA`.
- Risk: operator may configure T212/Web3 believing they are live paths.
- Required fix: either restore provider routing with tests or update docs and UI copy to reflect Alpaca-only active brokerage.

### P1-005: Terminal bridge/auth-session smoke failure remains in readiness docs

- Evidence: `test_terminal_command_integration` failed in extended post-recovery smoke because the test expected `session_token`.
- Risk: dashboard terminal command workflow may not match auth/login response contract.
- Required fix: decide whether API or test expectation is correct, then rerun smoke.

### P1-006: Historical Postgres auth failures and gRPC transport noise

- Evidence: production scan docs found repeated Postgres auth failures and gRPC broken pipe / reset events.
- Risk: order/audit writes or execution-engine calls may fail in active windows.
- Required proof: clean 24h logs or at minimum a clean extended soak with alert thresholds.

## P2: Medium Reliability And Data Quality Risks

### P2-001: Requirements are not fully pinned

- Location: `requirements.txt`.
- Risk: reproducibility drift in Docker/local builds.
- Required fix: generated lock/constraints file used by builds.

### P2-002: Market calendar handling is approximate

- Location: market-hours logic in monitor/config.
- Risk: cross-region equities may scan during wrong sessions or skip valid overlap windows.
- Required fix: exchange calendars and holidays.

### P2-003: Corporate actions are not a first-class invalidation path

- Risk: splits, symbol changes, and special dividends can corrupt Kalman state or hedge ratio.
- Required fix: corporate-action invalidation around pair state.

### P2-004: SEC/fundamental cache misses default neutral

- Risk: unknown fundamentals may pass live checks unless another veto fires.
- Required decision: stricter live-mode policy for unknown names.

### P2-005: Whale watcher depends on external cache freshness

- Risk: stale crypto context may understate large-flow risk.
- Required fix: stale-cache telemetry and ingestion health checks.

### P2-006: FastMCP and dashboard are separate public surfaces

- Risk: auth/exposure expectations may drift if ports are bound publicly.
- Required fix: explicit exposure model and deployment documentation.

## P3: Lower Priority But Keep Visible

### P3-001: Diagnostic output still bypasses structured logging in some paths

- Risk: dashboard log ingestion and alerting miss events.
- Required fix: replace stray prints/System.err style diagnostics when touching nearby code.

### P3-002: Pair universe is large and eligibility-driven

- Risk: provider rate limits, startup delay, and noisy rejection summaries.
- Required fix: watch pair rejection telemetry after pair edits.

## Closed Or Superseded Historical Items

Do not blindly resurrect old findings from `docs/bugs.md` or `.gemini/mvp_analysis.md`. Many were historical and may be fixed or superseded. Re-open only after proving the issue from current code.
