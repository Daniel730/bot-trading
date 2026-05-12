# Bug Ledger

## 2026-05-08 Concrete Bug Index

Canonical issue details live in `.brain/04_AUDIT_LEDGER.md` under the `ISSUE-XXXX` register. This ledger indexes the concrete code, config, log, test, or runtime bugs from the ecosystem audit so future work does not recreate duplicate IDs.

### Critical concrete bugs

| Issue | Title | Primary evidence | Status | Priority |
|---|---|---|---|---|
| ISSUE-0001 | Leg B non-terminal or partial fill is not persisted as monitored open exposure | `src/monitor.py::execute_trade`, `tests/unit/test_monitor.py::test_execute_trade_marks_partial_exposure_when_leg_b_not_terminal` | FIXED | P0 |
| ISSUE-0002 | Emergency close success only requires a positive fill quantity | `src/monitor.py::execute_trade`, `tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_partial_fill` | FIXED | P0 |
| ISSUE-0021 | Leg A full-fill gate accepts short `status=filled` quantity | `src/monitor.py::execute_trade`, `tests/unit/test_monitor.py::test_execute_trade_blocks_leg_b_when_leg_a_filled_quantity_is_short` | FIXED | P0 |
| ISSUE-0022 | Leg B terminal rejection after submit does not emergency-close Leg A | `src/monitor.py::execute_trade`, `tests/unit/test_monitor.py::test_execute_trade_emergency_closes_leg_a_when_leg_b_fill_rejects_after_submit` | FIXED | P0 |
| ISSUE-0024 | Financial kill switch uses gross market value for hedged and short positions | `src/monitor.py::_evaluate_exit_conditions`, `tests/unit/test_monitor.py::test_financial_kill_switch_uses_directional_pair_pnl` | FIXED | P0 |

### High concrete bugs and gates

| Issue | Title | Primary evidence | Status | Priority |
|---|---|---|---|---|
| ISSUE-0003 | Bid/ask provider masks missing quotes as zero-spread current price | `src/services/data_service.py::get_bid_ask`, `tests/unit/test_data_service_yfinance.py::test_get_bid_ask_missing_quote_does_not_fallback_to_zero_spread` | FIXED | P1 |
| ISSUE-0004 | Budget accounting updates on broker submission rather than confirmed fills | `src/services/brokerage_service.py::place_value_order`, `tests/unit/test_brokerage_service_budget.py` | FIXED | P1 |
| ISSUE-0005 | Broker and Web3 documentation conflicts with forced Alpaca routing | `src/config.py`, `tests/unit/test_config_broker_routes.py`, runtime docs | FIXED | P1 |
| ISSUE-0007 | Dashboard terminal auth smoke gate remains unresolved in readiness evidence | `docs/soak-fault-injection-report.md`, `tests/integration/test_terminal_bridge.py` | FIXED | P1 |
| ISSUE-0008 | Production approval lacks extended soak and active market evidence | `scripts/run_production_soak_gate.py`, `tests/unit/test_production_soak_gate.py` | FIXED | P0 |
| ISSUE-0009 | Runtime Postgres and gRPC transport faults lack an alert gate | `scripts/run_production_soak_gate.py`, `tests/unit/test_runtime_alert_rules.py` | FIXED | P1 |
| ISSUE-0011 | Corporate actions do not invalidate pair and Kalman state | `src/services/arbitrage_service.py`, `src/services/redis_service.py`, `tests/unit/test_arbitrage_state_invalidation.py` | FIXED | P1 |
| ISSUE-0012 | SEC/fundamental cache misses default to neutral in live signal path | `src/agents/orchestrator.py`, `tests/unit/test_orchestrator_fundamentals.py` | FIXED | P1 |
| ISSUE-0016 | Dashboard bot status mirrors desired state instead of unsafe operational state | `src/services/dashboard_service.py`, `src/monitor.py`, `tests/unit/test_dashboard_status.py` | FIXED | P1 |
| ISSUE-0018 | Dashboard wallet buy proceeds despite cash-limited planning | `src/services/dashboard_service.py::buy_wallet_recommendations`, `tests/unit/test_dashboard_wallet_sync.py` | FIXED | P1 |
| ISSUE-0023 | FastMCP trade tool bypasses dashboard safety and logs an invalid ledger payload | `src/mcp_server.py`, `tests/unit/test_mcp_execute_trade_safety.py` | FIXED | P1 |

### Medium concrete bugs and reliability gaps

| Issue | Title | Primary evidence | Status | Priority |
|---|---|---|---|---|
| ISSUE-0006 | Cash commands call a nonexistent brokerage ticker formatter | `src/services/brokerage_service.py`, `tests/unit/test_cash_ticker_formatter.py` | FIXED | P2 |
| ISSUE-0010 | Market session handling was suffix-based and Euronext calendars remained approximate | `src/monitor.py::get_market_config`, `src/monitor.py::is_market_open`, `tests/unit/test_market_calendar.py`, `docs/tofix.md` | FIXED | P2 |
| ISSUE-0013 | Whale watcher was configured and documented but active runtime was legacy-neutral | `src/agents/whale_watcher_agent.py`, `docs/STRATEGY.md`, `tests/unit/test_whale_watcher.py` | FIXED | P2 |
| ISSUE-0014 | Local runtime dependency path differs from CI and Docker | `README.md`, `docs/OPERATIONS.md`, `.github/workflows/deploy.yml`, `infra/Dockerfile` | OPEN | P2 |
| ISSUE-0015 | CI gates miss broker failure contracts and long-running safety scenarios | `.github/workflows/deploy.yml`, `docs/tofix.md`, readiness docs | OPEN | P2 |
| ISSUE-0017 | Fire-and-forget background tasks lack a watchdog | `src/monitor.py`, `src/services/persistence_service.py` | OPEN | P2 |
| ISSUE-0019 | Closing trades overwrites per-leg metadata | `src/services/persistence_service.py::close_trade` | OPEN | P2 |

### Low documentation bugs

| Issue | Title | Primary evidence | Status | Priority |
|---|---|---|---|---|
| ISSUE-0020 | Brain ledgers mix historical notes, closed invariants, and open production gates | `.brain/04_AUDIT_LEDGER.md`, `.brain/05_BUG_LEDGER.md` | OPEN | P3 |

### Previously protected invariants retained from earlier audits

These remain useful historical notes, but they are not blanket production approval:

- Successful fully filled pair entries persist as `OPEN_PAIR`.
- Leg B is blocked unless Leg A is confirmed full fill with positive quantity.
- Leg B is blocked when Leg A reports `status=filled` but the filled quantity is below the requested Leg A size.
- Delayed Leg B terminal rejection after accepted submit triggers Leg A emergency close instead of normal trade completion.
- Emergency close success requires the close filled quantity to cover the actual orphaned Leg A filled quantity.
- Financial kill switch uses directional pair PnL instead of gross market value for hedged/short positions.
- Alpaca ambiguous submit timeout reconciles by `client_order_id` and can return `unknown`.
- Unknown submit handling records manual reconciliation rather than retrying blindly.
- Normal close path waits for confirmed filled close snapshots and checks close quantity.
- Startup treats `CLOSING`/manual reconciliation states as unsafe.
- Paper-mode dashboard wallet actions avoid live broker calls.
- Monitor-level spread guard rejects explicit missing/zero bid/ask values.
- Value-order budget accounting waits for explicit filled results and `/invest` does not duplicate budget updates.
- Pending-order read failure blocks entry instead of assuming zero pending exposure.
- Alpaca broker read failures raise instead of returning safe-looking empty state.
- Unsupported `BROKERAGE_PROVIDER` values fail startup and docs describe Alpaca as the only active broker route.

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

### CLOSED: Value-order budget mutation before confirmed fill

- Fixed: `BrokerageService.place_value_order()` now updates used budget only for explicit `status=filled` results that are not marked `requires_reconciliation`; submitted `success` and `unknown` results do not mutate budget.
- Fixed: Telegram `/invest` no longer performs a second budget update after value-order submission.
- Corrected assumption: a non-error order submission is not equivalent to confirmed deployed capital.
- Protecting tests: `tests/unit/test_brokerage_service_budget.py::test_budget_updates_only_after_confirmed_fill`, `tests/unit/test_brokerage_service_budget.py::test_confirmed_fill_updates_budget_once`, `tests/unit/test_brokerage_service_budget.py::test_invest_command_does_not_update_budget_on_submit_success`.
- Validation command: `python -m pytest -q tests/unit/test_brokerage_service_budget.py tests/unit/test_brokerage_dispatcher.py tests/test_telegram_commands.py --asyncio-mode=auto`.
- Remaining risk: fill-confirmed accounting is not yet durable/idempotent across replay by broker order id.

### CLOSED: Unsupported broker/Web3 config silently coerced to Alpaca

- Fixed: `Settings` now rejects unsupported `BROKERAGE_PROVIDER` values instead of silently rewriting them to `ALPACA`.
- Fixed: runtime docs now describe Alpaca as the only active broker route, with Trading 212 and Web3 marked legacy/disabled.
- Corrected assumption: documented provider settings are not active live routes unless startup validation accepts them.
- Protecting test: `tests/unit/test_config_broker_routes.py::test_unsupported_broker_provider_fails_closed`.
- Validation command: `python -m pytest -q tests/unit/test_config_broker_routes.py tests/unit/test_config_env_parsing.py tests/unit/test_dashboard_config.py tests/unit/test_brokerage_service_provider.py --asyncio-mode=auto`.
- Remaining risk: legacy T212/Web3 code still exists in the repo and may need cleanup or stronger public-surface guards later.

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

- Status: closed 2026-05-08 in the active branch.
- Location: `infra/docker-compose.backend.yml`
- Root cause: backend Compose used `${POSTGRES_PASSWORD:-TBRZVATNGUXD}`, so missing environment configuration silently booted Postgres with a committed fallback password.
- Risk: containers could boot with a known/default database secret, directly contradicting `config.py`, `.env.template`, and docs.
- Fix: changed backend Compose to `${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}` so deployment fails fast unless the operator supplies the secret.
- Tests: added `tests/unit/test_backend_compose_secrets.py::test_backend_compose_requires_postgres_password_without_default`.
- Validation command: `python -m pytest -q tests/unit/test_backend_compose_secrets.py tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py tests/unit/test_validate_deploy_env.py --asyncio-mode=auto` passed with 53 passed.
- Remaining risk: this removes the backend Compose fallback only; production sign-off still needs P0-003, P0-004, and clean runtime/soak evidence.
- Next recommended task: verify and close P0-004 startup unresolved-state blocking evidence, or fix any gap found there.

### P0-002: Focused execution-safety test slice

- Status: closed 2026-05-08 in the active branch.
- Evidence before fix: 42 passed, 6 failed on 2026-05-07; 2026-05-08 rerun had 5 monitor failures from stale fixtures, real Postgres leakage, missing `max_allowed_fiat`, and stale profit-guard/orchestrator expectations.
- Risk: active fail-closed edits were not proven while monitor unit tests could hit real Postgres or bypass the current fill/reconciliation contract.
- Fix: updated monitor unit fixtures to provide confirmed fill snapshots, full risk metadata, explicit persistence mocks, and a profit-positive orchestrator-veto path.
- Tests updated: `test_execute_trade_success`, `test_close_position_skips_sell_when_broker_has_no_shares`, `test_execute_trade_crypto_live_uses_broker`, `test_execute_trade_crypto_budget_cap_applied`, and `test_orchestrator_veto`.
- Validation commands: `python -m pytest tests/unit/test_monitor.py -q --asyncio-mode=auto` passed with 17 passed; `python -m pytest -q tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py --asyncio-mode=auto` passed with 49 passed.
- Remaining risk: this closes the focused unit slice only; production sign-off still needs P0-001, P0-003, P0-004, and clean runtime/soak evidence.
- Next recommended task: verify and close P0-004 startup unresolved-state blocking evidence, or fix any gap found there.

### P0-003: Production remains not approved

- Status: closed 2026-05-08 as an automated fail-closed gate; actual production approval remains blocked until real evidence satisfies the gate.
- Evidence: `docs/production-scan-report.md` and `docs/soak-fault-injection-report.md`.
- Risk: functional tests and restart drills are encouraging, but not enough for live capital.
- Fix: added `scripts/run_production_soak_gate.py` to require longer soak, clean logs, full smoke, active scan cycle, recovery drills, and zero unresolved reconciliation rows before approval.
- Tests: added `tests/unit/test_production_soak_gate.py`.
- Validation command: `python -m pytest -q tests/unit/test_production_soak_gate.py tests/unit/test_validate_deploy_env.py tests/unit/test_backend_compose_secrets.py`.
- Remaining risk: no real `docs/production-soak-evidence.json` exists yet, so the gate correctly blocks production approval.
- Next recommended task: verify and close ISSUE-0007 terminal command auth smoke evidence, or fix any gap found there.

### P0-004: Unresolved execution state must block startup

- Status: closed 2026-05-08 in the active branch.
- Location: `src/services/persistence_service.py`, startup unsafe-state reconciliation.
- Root cause: startup recovery counted `CLOSING`, `NEEDS_MANUAL_RECONCILIATION`, and `FAILED_REQUIRES_MANUAL_RECONCILIATION`, but not `CLOSE_FAILED`.
- Risk: after a close exception, the ledger could be left in `CLOSE_FAILED` and the next startup could continue scanning instead of pausing for broker/ledger reconciliation.
- Fix: include `OrderStatus.CLOSE_FAILED` in the startup unresolved-state count so `_fail_fast_on_unresolved_execution_state()` blocks startup.
- Tests: added `tests/unit/test_startup_guards.py::test_startup_treats_close_failed_as_unresolved_execution_state`.
- Validation command: `python -m pytest -q tests/unit/test_backend_compose_secrets.py tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py tests/unit/test_validate_deploy_env.py --asyncio-mode=auto` passed with 54 passed.
- Remaining risk: production sign-off still needs P0-003 runtime/soak evidence and no unresolved manual-reconciliation rows before actual runs.
- Next recommended task: add end-to-end partial-fill contract coverage for P1-002, starting with Leg B/close partial fills.

## P1: High Financial Or Workflow Risk

### P1-001: Alpaca ambiguous submit handling is under active audition

- Location: `src/services/brokerage/alpaca.py`, `src/monitor.py`.
- Current direction: reconcile by `client_order_id`; return `unknown` if not reconciled; monitor must not resubmit blindly.
- Risk: timeouts after broker accept can otherwise duplicate orders.
- Required proof: tests for timeout reconciled, timeout unreconciled, no fallback submit, monitor manual reconciliation.

### P1-002: Partial fills are still not fully end-to-end modeled

- Status: open for broader partial-fill lifecycle coverage; normal close and emergency-close partial-fill quantity gaps fixed 2026-05-08 in the active branch.
- Current direction: monitor blocks leg B unless leg A is fully confirmed.
- Fixed in this patch: `_close_position()` no longer closes the ledger when a close snapshot reports `status=filled` but `filled_qty` is below the requested close quantity.
- Files changed: `src/monitor.py`, `tests/unit/test_monitor.py`.
- Tests added: `tests/unit/test_monitor.py::test_close_position_does_not_close_ledger_on_short_close_fill_quantity`.
- Validation command: `python -m pytest -q tests/unit/test_backend_compose_secrets.py tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py tests/unit/test_validate_deploy_env.py --asyncio-mode=auto` passed with 59 passed.
- Remaining risk: broader partial-fill lifecycle coverage remains open, but ISSUE-0001 now protects monitor visibility for Leg B non-terminal exposure.
- Next recommended task: verify and close ISSUE-0007 terminal command auth smoke evidence, or fix any gap found there.

### P1-003: Close workflow can create ledger/broker divergence if not fully confirmed

- Current direction: require close fill snapshots before ledger closure.
- Risk: a close submit can be accepted but the process can crash before ledger update.
- Current update: ledger closure and Leg-B emergency close success now require close-fill confirmation; unknown or unconfirmed close states update manual reconciliation.
- Still open: one close fill confirmed then second close unknown/fails, and startup requiring manual reconciliation.
- Required proof: tests for one close fill confirmed then second close unknown/fails, and startup requiring manual reconciliation.

### P1-007: Account balance reads on broker failure

- Status: closed 2026-05-08 in the active branch.
- Location: `src/services/brokerage/alpaca.py`, `src/monitor.py`.
- Root cause: `get_account_cash()`, `get_account_equity()`, and `get_account_buying_power()` logged provider read failures and returned `0.0`.
- Risk: unavailable account state could look like depleted funds, blocking entries for the wrong reason and corrupting dashboard/budget diagnostics.
- Fix: Alpaca account reads now re-raise provider failures; live `execute_trade()` catches account-state read failures, alerts the operator, and blocks before risk sizing or broker orders.
- Tests: added `tests/unit/test_alpaca_provider.py::test_alpaca_account_reads_raise_on_api_failure` and `tests/unit/test_monitor.py::test_execute_trade_blocks_when_account_balance_read_fails`.
- Validation command: `python -m pytest -q tests/unit/test_backend_compose_secrets.py tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py tests/unit/test_validate_deploy_env.py --asyncio-mode=auto` passed with 58 passed.
- Remaining risk: `_get_sizing_base()` still falls back for signal-preview sizing if equity reads fail; this patch closes the live execution entry gate only.
- Next recommended task: add end-to-end partial-fill contract coverage for P1-002, starting with Leg B/close partial fills.

### P1-008: Emergency close success fill confirmation

- Status: closed 2026-05-08 in the active branch.
- Location: `src/monitor.py`, Leg B rejection emergency close branch.
- Root cause: emergency close `unknown` was manual reconciliation, but a `success` submit still logged emergency close success without polling for actual fill.
- Risk: Leg A directional exposure could remain open while logs implied it was closed.
- Fix: after emergency close submit success, poll the close order by broker/client order ID; if the fill is missing, non-filled, partial, or zero quantity, persist `FAILED_REQUIRES_MANUAL_RECONCILIATION` with `reason=emergency_close_unconfirmed`.
- Tests: updated/protected `tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_fill_unconfirmed`; updated `tests/unit/test_monitor.py::test_execute_trade_emergency_closes_leg_a_when_leg_b_fails`; added `tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_partial_fill` to prove success requires close-fill quantity completeness.
- Validation command: `python -m pytest -q tests/unit/test_monitor.py tests/unit/test_alpaca_provider.py tests/unit/test_spread_guard_unit.py tests/unit/test_startup_guards.py --asyncio-mode=auto`.
- Remaining risk: broader execution safety still depends on real soak evidence passing the gate added under ISSUE-0008.
- Next recommended task: verify and close ISSUE-0007 terminal command auth smoke evidence, or fix any gap found there.

### P1-004: Documentation and implementation disagree on live venues

- Status: closed 2026-05-09 in the active branch as ISSUE-0005.
- Docs: Runtime docs now describe Alpaca as the only active broker route; Trading 212 and Web3 are legacy/disabled.
- Current code: `Settings` rejects unsupported `BROKERAGE_PROVIDER` values; `BrokerageService` still forces Alpaca.
- Tests: added `tests/unit/test_config_broker_routes.py::test_unsupported_broker_provider_fails_closed`.
- Remaining risk: legacy provider code still exists and may need later cleanup or stronger public-surface guards.
- Next recommended task: verify and close ISSUE-0007 terminal command auth smoke evidence, or fix any gap found there.

### P1-005: Terminal bridge/auth-session smoke failure remains in readiness docs

- Status: closed 2026-05-09 as ISSUE-0007.
- Evidence before fix: `test_terminal_command_integration` failed in extended post-recovery smoke because the test expected `session_token` from the initial login response.
- Root cause: the smoke helper assumed token-only login immediately completed a session, but the current dashboard auth flow returns a pending challenge and only returns `session_token` from `/api/auth/login/complete`.
- Fix: update the integration helper to keep `TestClient` alive, stub external notification/message sends, complete the approval challenge, and then call terminal commands with the returned session.
- Tests: `tests/integration/test_terminal_bridge.py::test_terminal_command_integration` and `tests/integration/test_terminal_bridge.py::test_terminal_approval_integration`.
- Validation command: `python -m pytest tests/integration/test_terminal_bridge.py::test_terminal_command_integration tests/integration/test_terminal_bridge.py::test_terminal_approval_integration -q --asyncio-mode=auto` passed with 2 passed.
- Remaining risk: production approval still needs ISSUE-0009 and full soak/active-market evidence; `test_audit_logging` still depends on real Postgres through `/exposure`.
- Next recommended task: ISSUE-0009 runtime Postgres and gRPC transport faults lack an alert gate.

### P1-006: Historical Postgres auth failures and gRPC transport noise

- Status: closed 2026-05-09 as ISSUE-0009.
- Evidence before fix: production scan docs found repeated Postgres auth failures and gRPC broken pipe / reset events, while the production soak gate accepted otherwise-complete evidence with no runtime error threshold checks.
- Root cause: `scripts/run_production_soak_gate.py` trusted `clean_log_window=true` without requiring explicit Postgres/gRPC error counts.
- Fix: the soak gate now requires `runtime_error_counts.postgres_auth_failures`, `postgres_auth_timeouts`, `grpc_broken_pipe_errors`, and `grpc_connection_reset_errors` to be present and equal to `0`.
- Tests: added `tests/unit/test_runtime_alert_rules.py::test_postgres_and_grpc_error_spikes_fail_soak_gate`; updated `tests/unit/test_production_soak_gate.py` complete evidence fixtures.
- Validation command: `python -m pytest -q tests/unit/test_runtime_alert_rules.py tests/unit/test_production_soak_gate.py tests/unit/test_validate_deploy_env.py tests/unit/test_backend_compose_secrets.py` passed with 7 passed.
- Remaining risk: this is a production evidence gate, not live alert delivery; broader alerting for API non-2xx, order rejects, timeouts, and kill-switch activations remains in the release checklist.
- Next recommended task: ISSUE-0011 corporate actions do not invalidate pair/Kalman state.

### P1-007: Corporate-action adjusted history invalidates Kalman state

- Status: closed 2026-05-09 as ISSUE-0011.
- Evidence before fix: `get_or_create_filter()` warm-started solely by `pair_id`, and Redis Kalman state had no version or data fingerprint.
- Root cause: saved Kalman state was assumed valid whenever the pair id was unchanged, even if adjusted historical prices changed after splits, dividends, symbol changes, or data remaps.
- Fix: compute a `history-v1` fingerprint from pair id plus prewarm history, store it with Redis Kalman state, and rebuild the filter when the saved fingerprint does not match the current history.
- Tests: added `tests/unit/test_arbitrage_state_invalidation.py::test_kalman_state_invalidates_on_corporate_action`.
- Validation command: `python -m pytest -q tests/unit/test_arbitrage_state_invalidation.py tests/unit/test_arbitrage_math.py tests/unit/test_kalman.py tests/unit/test_kalman_q_inflation.py tests/unit/test_rolling_cointegration.py` passed with 20 passed.
- Remaining risk: this covers adjusted-history fingerprint changes during prewarm/reload, not a full corporate-action event ingestion pipeline.
- Next recommended task: ISSUE-0006 Cash commands call nonexistent `_format_ticker`.

### P1-008: SEC/fundamental cache misses default neutral in live path

- Status: closed 2026-05-09 as ISSUE-0012.
- Evidence before fix: `redis_service.get_fundamental_score()` returning `None` caused `src/agents/orchestrator.py` to log a cache miss and substitute `ORCH_FUNDAMENTAL_DEFAULT_SCORE`.
- Root cause: missing fundamental state was assumed safe to represent as the configured neutral default, even when `PAPER_TRADING=false`.
- Risk: a live-mode signal for a structurally unknown ticker could pass the SEC/fundamental gate and continue into portfolio weighting.
- Fix: live or `LIVE_CAPITAL_DANGER` mode now records unknown fundamental tickers, sets a fundamental veto, and returns `final_confidence=0.0` before portfolio advice is requested.
- Tests: added `tests/unit/test_orchestrator_fundamentals.py::test_live_mode_vetoes_missing_fundamental_score`.
- Validation command: `python -m pytest -q tests/unit/test_orchestrator_fundamentals.py tests/unit/test_orchestrator_mab.py tests/unit/test_sector_leader_regime.py::test_orchestrator_sector_veto tests/unit/test_sector_leader_regime.py::test_orchestrator_missing_sector_defaults_to_spy` passed with 4 passed.
- Remaining risk: stale-but-present fundamental cache entries still lack a max-age/freshness guard.
- Next recommended task: ISSUE-0006 Cash commands call nonexistent `_format_ticker`.

### P1-009: Dashboard status mirrors desired state instead of unsafe operational state

- Status: closed 2026-05-11 as ISSUE-0016.
- Evidence before fix: `DashboardService.build_summary()` returned `bot_status` from `dashboard_state.desired_bot_state`, and startup fail-fast persisted manual review without updating dashboard state.
- Root cause: dashboard display state treated the operator-requested state as equivalent to actual runtime safety state.
- Risk: the operator could see `RUNNING` while startup had paused for unresolved ledger/broker reconciliation.
- Fix: summary now includes `desired_bot_state`, persisted `operational_status`, and `blocked`; non-`NORMAL` operational status overrides `bot_status`. Startup fail-fast also updates dashboard stage to `PAUSED_REQUIRES_MANUAL_REVIEW`, and the React shell now prefers summary `bot_status` over stream desired state.
- Tests: added `tests/unit/test_dashboard_status.py::test_summary_reports_manual_review_after_startup_fail_fast`; updated `tests/unit/test_startup_guards.py::test_startup_blocks_when_unresolved_execution_state_exists`.
- Validation command: `python -m pytest -q tests/unit/test_dashboard_status.py tests/unit/test_dashboard_config.py tests/unit/test_dashboard_sessions.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_startup_guards.py` passed with 19 passed; `node node_modules/typescript/bin/tsc -b` passed from `frontend/`.
- Remaining risk: frontend lint still has pre-existing unrelated failures in `LoginView.test.tsx` and `useStartupProgress.ts`.
- Next recommended task: ISSUE-0006 Cash commands call nonexistent `_format_ticker`.

### P1-010: Dashboard wallet buy proceeds despite cash-limited planning

- Status: closed 2026-05-11 as ISSUE-0018.
- Evidence before fix: `calculate_wallet_recommendations()` set `cash_limited=true`, but `buy_wallet_recommendations()` logged that state and continued to build a plan and place orders.
- Root cause: the dashboard treated broker rejection as the final budget gate instead of enforcing its own known cash-limit state.
- Risk: a dashboard wallet buy could submit orders despite the dashboard already knowing requested budget exceeded effective broker cash, producing avoidable rejections or partial allocation.
- Fix: `buy_wallet_recommendations()` now raises `HTTPException(400)` before recommendation filtering, planning, or order placement when `cash_limited=true`.
- Tests: added `tests/unit/test_dashboard_wallet_sync.py::test_wallet_buy_blocks_when_cash_limited`.
- Validation command: `python -m pytest -q tests/unit/test_dashboard_wallet_sync.py tests/unit/test_dashboard_wallet_new_methods.py tests/unit/test_dashboard_config.py tests/unit/test_dashboard_status.py` passed with 12 passed.
- Remaining risk: no explicit operator override/cap-to-cash workflow exists; cash-limited wallet buys now fail closed.
- Next recommended task: ISSUE-0006 Cash commands call nonexistent `_format_ticker`.

### P1-011: FastMCP trade tool bypasses dashboard safety and logs invalid ledger payload

- Status: closed 2026-05-11 as ISSUE-0023.
- Evidence before fix: `src/mcp_server.py::execute_trade` accepted ticker/side/quantity, called `execution_client.execute_trade()` directly, and attempted a ledger write with `metadata` instead of `metadata_json`.
- Root cause: the optional FastMCP surface treated manual execution as equivalent to the monitor/dashboard execution workflow.
- Risk: an exposed control surface could bypass paper/live, risk, quote, and reconciliation gates, and the audit write could fail with an invalid payload.
- Fix: `execute_trade` now fails closed with a rejected/disabled response before any gRPC execution or ledger write.
- Tests: added `tests/unit/test_mcp_execute_trade_safety.py::test_mcp_execute_trade_rejects_or_uses_safe_ledger_payload`.
- Validation command: `python -m pytest -q tests/unit/test_mcp_execute_trade_safety.py::test_mcp_execute_trade_rejects_or_uses_safe_ledger_payload --asyncio-mode=auto` passed.
- Remaining risk: no safe monitor-routed FastMCP execution path exists; adjacent idempotency tests require the unavailable `mocker` fixture locally.
- Next recommended task: ISSUE-0006 Cash commands call nonexistent `_format_ticker`.

## P2: Medium Reliability And Data Quality Risks

### P2-001: Cash commands call a nonexistent brokerage ticker formatter

- Status: closed 2026-05-11 as ISSUE-0006.
- Evidence before fix: `/cash` and `CashManagementService.liquidate_for_trade()` called `brokerage._format_ticker(...)`, but `BrokerageService` did not implement it.
- Root cause: cash/sweep workflows assumed the brokerage facade exposed ticker normalization.
- Risk: operator cash visibility and sweep liquidation could fail with `AttributeError`, increasing manual debugging burden during liquidity checks.
- Fix: `BrokerageService._format_ticker()` now strips whitespace and uppercases symbols.
- Tests: added `tests/unit/test_cash_ticker_formatter.py::test_cash_command_uses_real_ticker_formatter` and `tests/unit/test_cash_ticker_formatter.py::test_cash_management_liquidate_uses_real_ticker_formatter`.
- Validation command: `python -m pytest -q tests/unit/test_cash_ticker_formatter.py tests/test_telegram_commands.py tests/unit/test_brokerage_service_provider.py --asyncio-mode=auto` passed with 11 passed.
- Remaining risk: cash-command UX and sweep execution safety are otherwise unchanged.
- Next recommended task was ISSUE-0010, then ISSUE-0013; after both 2026-05-12 fixes, continue with ISSUE-0014 Local runtime dependency path differs from CI and Docker.

### P2-002: Requirements are not fully pinned

- Location: `requirements.txt`.
- Risk: reproducibility drift in Docker/local builds.
- Required fix: generated lock/constraints file used by builds.

### P2-003: Market calendar handling was approximate

- Location: market-hours logic in monitor/config.
- Risk: cross-region equities may scan during wrong sessions or skip valid overlap windows.
- 2026-05-12 update: full-day holiday blocking now exists for default US equities and current suffix venues.
- 2026-05-12 update: default US equities now close at 13:00 ET on recurring NYSE early-close dates.
- 2026-05-12 update: `.HK` symbols now use Hong Kong local hours and common HKEX noon early-close dates.
- 2026-05-12 update: `.L` symbols now close at 12:30 London time on common LSE half-days.
- 2026-05-12 update: `.DE` symbols now block Xetra Christmas Eve and New Year's Eve closures.
- 2026-05-12 update: `.AS` and `.PA` symbols now use local Amsterdam/Paris sessions and common 14:05 CET Euronext half-day closes.
- Status: closed as ISSUE-0010 for scoped configured calendar coverage.

### P2-004: Corporate actions are not a first-class invalidation path

- Risk: splits, symbol changes, and special dividends can corrupt Kalman state or hedge ratio.
- Required fix: corporate-action invalidation around pair state.

### P2-005: SEC/fundamental cache misses default neutral

- Risk: unknown fundamentals may pass live checks unless another veto fires.
- Required decision: stricter live-mode policy for unknown names.

### P2-006: Whale watcher is legacy-inactive in active runtime

- Risk: no active whale-flow risk analysis is applied.
- Status: closed as ISSUE-0013 for disclosure/status safety; restoring cache-backed whale analysis is a future feature and should require fresh issue scope plus tests.

### P2-007: FastMCP and dashboard are separate public surfaces

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
