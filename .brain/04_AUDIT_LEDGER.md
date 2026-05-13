# Audit Ledger

## 2026-05-08 Ecosystem Audit Canonical Register

This section is the canonical issue register for the 2026-05-08 ecosystem audit. Historical notes below are preserved as supporting context, but open remediation should use the `ISSUE-XXXX` IDs here.

### ISSUE-0001 — Leg B non-terminal or partial fill is not persisted as monitored open exposure

Status: FIXED  
Severity: CRITICAL  
Area: execution  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-08  
Evidence type: code  
Confidence: HIGH  

#### Summary
When Leg A fills and Leg B is accepted but does not reach a terminal full fill within the 30 second poll window, the monitor can leave rows in leg-level statuses that are not returned by the open-position query. That can hide partial directional exposure from restart recovery and exit monitoring.

#### Evidence
- `src/monitor.py::execute_trade` sets `status_b = LEG_B_SUBMITTED` when `fill_b` is absent and `status_b = LEG_B_PARTIAL` for partial fills.
- `src/monitor.py::execute_trade` computes `pair_status = PARTIAL_EXPOSURE`, but the final per-leg journal write uses leg-level statuses unless the pair is fully `OPEN_PAIR`.
- `src/services/persistence_service.py::get_open_signals` only queries `OPEN`, `OPEN_PAIR`, `PARTIAL_EXPOSURE`, and `CLOSING`; it excludes `LEG_B_SUBMITTED` and `LEG_B_PARTIAL`.
- `git grep` found no focused tests for `LEG_B_PARTIAL`.

#### Trigger
Leg A receives a confirmed full fill, Leg B is submitted, and Leg B is still pending/non-terminal or only partially filled after the fill polling timeout.

#### Broken assumption
A leg-level submitted or partial status is assumed to be sufficiently visible to the exit/reconciliation workflow.

#### Financial or workflow consequence
The account may hold one-sided or partly hedged exposure while restart recovery and normal exit monitoring fail to treat the signal as open. This can miss exits, duplicate later exposure, or require manual broker cleanup after losses have already moved.

#### Existing protection
Leg B non-terminal state sends a notification, fully successful pairs become `OPEN_PAIR`, and final non-terminal/partial rows now persist as `PARTIAL_EXPOSURE` while retaining leg-specific status in metadata.

#### Missing protection
None for this issue after the 2026-05-08 fix. Broader reconciliation and runtime evidence gaps remain tracked separately.

#### Smallest safe fix
Persist the signal as `PARTIAL_EXPOSURE` whenever Leg B is non-terminal or partial, or extend the open-signal query and close/reconciliation path to include those leg-level statuses.

#### Test required
Simulate Leg A fully filled and Leg B non-terminal/partial; assert the persisted signal is returned by `get_open_signals()` and startup recovery/exit monitoring cannot skip it.

#### Validation command
`python -m pytest tests/unit/test_monitor.py::test_execute_trade_marks_partial_exposure_when_leg_b_not_terminal -q --asyncio-mode=auto`

#### Related issues
ISSUE-0002, ISSUE-0016, ISSUE-0019

#### Fix priority
P0

#### Notes
This is distinct from the already protected Leg A ambiguity path. The risk appears after Leg A is safely filled and Leg B has already been sent.

Fixed 2026-05-08 in `src/monitor.py::execute_trade` by persisting final pair rows as `PARTIAL_EXPOSURE` whenever Leg B is non-terminal or partial, preserving the leg-level status under `metadata_json.order_status`. Regression test added: `tests/unit/test_monitor.py::test_execute_trade_marks_partial_exposure_when_leg_b_not_terminal`. Validation passed: `python -m pytest -q tests/unit/test_monitor.py tests/unit/test_alpaca_provider.py tests/unit/test_spread_guard_unit.py tests/unit/test_startup_guards.py --asyncio-mode=auto`.

### ISSUE-0002 — Emergency close success only requires a positive fill quantity

Status: FIXED  
Severity: CRITICAL  
Area: exit  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-08  
Evidence type: code  
Confidence: HIGH  

#### Summary
The emergency-close branch used after Leg B rejection treats a close as successful when the close order reports `status=filled` and `filled_qty > 0`. It does not require the close fill quantity to equal the original Leg A exposure.

#### Evidence
- `src/monitor.py::execute_trade` emergency-close branch reads `close_filled_qty` and checks `close_status_raw != "filled" or close_filled_qty <= 0`.
- `src/monitor.py::_close_position` has a stricter later close path that compares `close_filled_qty` to `expected_close_qty`, showing the safer invariant exists elsewhere.
- Existing `.brain/05_BUG_LEDGER.md` notes the remaining emergency-close quantity-completeness gap.

#### Trigger
Leg A fills, Leg B is rejected, the bot submits an emergency close for Leg A, and the broker reports a partial close fill with a positive filled quantity.

#### Broken assumption
Any positive emergency-close fill is assumed to remove the whole orphaned Leg A position.

#### Financial or workflow consequence
The bot can log emergency close success while residual shares remain live at the broker. That creates unmanaged live exposure and can miss subsequent liquidation or stop-loss handling.

#### Existing protection
Emergency close is attempted after Leg B rejection, and the branch detects unknown/unfilled close orders.

#### Missing protection
No expected-quantity comparison in this emergency-close path.

#### Smallest safe fix
Compare `close_filled_qty` with the original Leg A filled quantity and mark `FAILED_REQUIRES_MANUAL_RECONCILIATION` unless the close is fully filled.

#### Test required
Simulate Leg B rejection and emergency close returning `status=filled` with `filled_qty` below the Leg A filled quantity; assert manual reconciliation and no success message.

#### Validation command
`python -m pytest tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_partial_fill -q --asyncio-mode=auto`

#### Related issues
ISSUE-0001, ISSUE-0019

#### Fix priority
P0

#### Notes
This is the smallest high-confidence P0 because the safer quantity check is already present in the normal close path.

Fixed 2026-05-08 in `src/monitor.py::execute_trade` by requiring emergency-close filled quantity to cover the actual Leg A filled quantity before treating the orphan close as safe. Regression test added: `tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_partial_fill`. Validation passed: `python -m pytest -q tests/unit/test_monitor.py tests/unit/test_alpaca_provider.py tests/unit/test_spread_guard_unit.py tests/unit/test_startup_guards.py --asyncio-mode=auto`.

### ISSUE-0003 — Bid/ask provider masks missing quotes as zero-spread current price

Status: FIXED  
Severity: HIGH  
Area: data  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-08  
Evidence type: code  
Confidence: HIGH  

#### Summary
`DataService.get_bid_ask()` turns missing bid or ask into `(currentPrice, currentPrice)`, making the spread look executable and zero. The monitor's spread guard rejects zero or invalid quotes, but this provider fallback hides the missing quote condition before the guard sees it.

#### Evidence
- `src/services/data_service.py::get_bid_ask` reads yfinance `bid` and `ask`; if either is `0.0`, it returns `currentPrice` or `previousClose` for both sides.
- `src/monitor.py::execute_trade` checks combined bid/ask spread before risk sizing and broker order submission.
- `tests/unit/test_spread_guard_unit.py::test_spread_guard_rejects_missing_bid_ask` protects monitor behavior when `(0, 0)` is returned, but does not test the provider fallback that converts missing quotes to a valid-looking zero spread.

#### Trigger
yfinance lacks bid/ask for a symbol, commonly after hours, during illiquidity, or for unsupported instruments, but still exposes `currentPrice` or `previousClose`.

#### Broken assumption
Last/current price is treated as an executable bid and ask.

#### Financial or workflow consequence
The bot can pass the spread guard on stale or non-executable data, understate friction, and submit orders for a signal that should have been blocked.

#### Existing protection
The monitor rejects non-positive bid/ask values and excessive spreads. `DataService.get_bid_ask()` now preserves missing executable bid/ask as `(0.0, 0.0)` instead of fabricating a zero-spread quote from `currentPrice` or `previousClose`.

#### Missing protection
None for this issue after the 2026-05-08 fix. Broader quote freshness/session risks remain tracked under related issues.

#### Smallest safe fix
Return `(0.0, 0.0)` or a structured invalid quote when bid/ask is missing, then let the existing guard block execution.

#### Test required
Mock yfinance info with `bid=0`, `ask=0`, and `currentPrice>0`; assert `get_bid_ask()` produces a value that causes execution to reject rather than zero-spread acceptance.

#### Validation command
`python -m pytest tests/unit/test_data_service_yfinance.py::test_get_bid_ask_missing_quote_does_not_fallback_to_zero_spread -q`

#### Related issues
ISSUE-0010, ISSUE-0015

#### Fix priority
P1

#### Notes
This is a data issue with execution consequences. It can break live behavior while unit tests focused on monitor-level guard logic still pass.

Fixed 2026-05-08 in `src/services/data_service.py::get_bid_ask` by returning `(0.0, 0.0)` for missing, non-positive, or non-numeric bid/ask values. Regression test added: `tests/unit/test_data_service_yfinance.py::test_get_bid_ask_missing_quote_does_not_fallback_to_zero_spread`. Validation passed: `python -m pytest -q tests/unit/test_data_service_yfinance.py::test_get_bid_ask_missing_quote_does_not_fallback_to_zero_spread tests/unit/test_spread_guard_unit.py tests/unit/test_monitor.py tests/unit/test_alpaca_provider.py tests/unit/test_startup_guards.py --asyncio-mode=auto`.

### ISSUE-0004 — Budget accounting updates on broker submission rather than confirmed fills

Status: FIXED  
Severity: HIGH  
Area: risk  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-08  
Evidence type: code/test  
Confidence: HIGH  

#### Summary
Live budget accounting incremented when a broker submission did not return `status=error`, not when a fill was confirmed. The Telegram `/invest` path could also update budget again after the brokerage service already did.

#### Evidence
- Before the fix, `src/services/brokerage_service.py::place_value_order` called `budget_service.update_used_budget()` for any non-error live result.
- Before the fix, ambiguous broker results could return `status=unknown` / `requires_reconciliation`, which still passed the non-error budget update condition.
- Before the fix, `src/services/notification_service.py::_handle_invest` called `brokerage.place_value_order()` and then called `budget_service.update_used_budget("ALPACA", amount)` again on non-error result.
- `tests/unit/test_brokerage_service_budget.py::test_budget_updates_only_after_confirmed_fill` now proves submitted and unknown value-order results do not mutate budget.
- `tests/unit/test_brokerage_service_budget.py::test_confirmed_fill_updates_budget_once` now proves explicit `status=filled` results update budget once using filled notional.
- `tests/unit/test_brokerage_service_budget.py::test_invest_command_does_not_update_budget_on_submit_success` now proves `/invest` does not duplicate budget accounting after submit success.

#### Trigger
A live order is accepted but not filled, becomes unknown, partially fills, or is submitted through `/invest`.

#### Broken assumption
Submitted or non-error order response is treated as equivalent to confirmed deployed capital.

#### Financial or workflow consequence
Budget can drift away from actual broker exposure, blocking safe trades or allowing wrong future sizing. The `/invest` path can double-count budget and make the dashboard/operator view unreliable.

#### Existing protection
The monitor also checks pending broker order value before new pair execution. `BrokerageService.place_value_order()` now mutates live budget only when the normalized provider result is explicitly `status=filled` and not marked `requires_reconciliation`. `/invest` no longer performs its own post-submit budget mutation.

#### Missing protection
No durable idempotent budget transaction keyed by broker order/signal. This fix prevents pre-fill and duplicate mutation, but replay/idempotency for future fill-confirmed accounting remains a broader accounting-hardening risk.

#### Smallest safe fix
Update live budget only from explicit filled value-order results and remove the duplicate `/invest` update.

#### Test required
Assert unknown/accepted-but-unfilled submissions do not increment used budget, explicit filled results increment once, and `/invest` submit success does not perform a duplicate budget update.

#### Validation command
`python -m pytest -q tests/unit/test_brokerage_service_budget.py tests/unit/test_brokerage_dispatcher.py tests/test_telegram_commands.py --asyncio-mode=auto`

#### Related issues
ISSUE-0001, ISSUE-0018

#### Fix priority
P1

#### Notes
Fixed 2026-05-08 in `src/services/brokerage_service.py` and `src/services/notification_service.py`. Tests added/updated in `tests/unit/test_brokerage_service_budget.py`, `tests/unit/test_brokerage_dispatcher.py`, and `tests/test_telegram_commands.py`. Broad focused validation passed: `python -m pytest -q tests/unit/test_brokerage_service_budget.py tests/unit/test_brokerage_dispatcher.py tests/test_telegram_commands.py tests/unit/test_backend_compose_secrets.py tests/unit/test_production_soak_gate.py tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py tests/unit/test_validate_deploy_env.py --asyncio-mode=auto` with 80 passed. Remaining risk: budget fill accounting is still not durable/idempotent across replay; next recommended task is ISSUE-0007 after ISSUE-0005 was fixed.

### ISSUE-0005 — Broker and Web3 documentation conflicts with forced Alpaca routing

Status: FIXED  
Severity: HIGH  
Area: config  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-09  
Evidence type: config/doc/test  
Confidence: HIGH  

#### Summary
Operator documentation advertised Trading 212, Alpaca, and Web3 routing, while runtime configuration forced Alpaca and disabled Web3. This created paper/live and broker-selection confusion.

#### Evidence
- Before the fix, `README.md` said `BROKERAGE_PROVIDER=T212` selected Trading 212 and described Web3 routing.
- Before the fix, `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, and `docs/STRATEGY.md` described `BROKERAGE_PROVIDER=T212|ALPACA` and Web3 live crypto paths.
- Before the fix, `src/config.py::validate_secrets` assigned `self.BROKERAGE_PROVIDER = "ALPACA"` instead of rejecting unsupported values.
- Before the fix, `src/config.py` also assigned `settings.BROKERAGE_PROVIDER = "ALPACA"` after settings overrides.
- `src/config.py::web3_enabled` returns `False`.
- `tests/unit/test_config_broker_routes.py::test_unsupported_broker_provider_fails_closed` now proves `BROKERAGE_PROVIDER=T212` and `BROKERAGE_PROVIDER=WEB3` fail configuration.
- Current README and operations/architecture/strategy/budget docs state Alpaca-only active routing and legacy/disabled T212/Web3 routes.

#### Trigger
An operator sets `BROKERAGE_PROVIDER=T212` or `BROKERAGE_PROVIDER=WEB3` expecting the historical/documented execution route.

#### Broken assumption
Docs and environment variables are assumed to reflect the active execution route.

#### Financial or workflow consequence
The bot can run against a different venue than the operator expects, invalidating live/paper testing assumptions and making deployment review misleading.

#### Existing protection
Runtime code currently forces a single Alpaca route, which avoids accidental T212/Web3 live activation. Configuration now fails startup for unsupported `BROKERAGE_PROVIDER` values instead of silently coercing them. Dashboard config already exposes only `ALPACA`.

#### Missing protection
None for the core unsupported-provider config path after the 2026-05-09 fix.

#### Smallest safe fix
Fail startup when unsupported broker/Web3 settings are requested, and align docs with the active Alpaca-only route.

#### Test required
Set `BROKERAGE_PROVIDER=T212` and `BROKERAGE_PROVIDER=WEB3` in a config test and assert startup fails with an explicit unsupported-route error.

#### Validation command
`python -m pytest -q tests/unit/test_config_broker_routes.py tests/unit/test_config_env_parsing.py tests/unit/test_dashboard_config.py tests/unit/test_brokerage_service_provider.py --asyncio-mode=auto`

#### Related issues
ISSUE-0014, ISSUE-0015

#### Fix priority
P1

#### Notes
Fixed 2026-05-09 in `src/config.py` by rejecting unsupported active broker providers instead of silently coercing them to Alpaca. Regression test added: `tests/unit/test_config_broker_routes.py::test_unsupported_broker_provider_fails_closed`. Docs updated: `README.md`, `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, `docs/STRATEGY.md`, `docs/DEVELOPER_BUDGET_GUIDE.md`, and `docs/needs-to-analyse.md`. Validation passed: `python -m pytest -q tests/unit/test_config_broker_routes.py tests/unit/test_config_env_parsing.py tests/unit/test_dashboard_config.py tests/unit/test_brokerage_service_provider.py tests/unit/test_brokerage_service_budget.py tests/unit/test_brokerage_dispatcher.py tests/test_telegram_commands.py tests/unit/test_backend_compose_secrets.py tests/unit/test_production_soak_gate.py tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py tests/unit/test_validate_deploy_env.py --asyncio-mode=auto` with 91 passed. Remaining risk: legacy T212/Web3 code still exists in the repo and may need cleanup or stronger public-surface guards later; next recommended task is ISSUE-0007.

### ISSUE-0006 — Cash commands call a nonexistent brokerage ticker formatter

Status: FIXED  
Severity: MEDIUM  
Area: frontend  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-11  
Evidence type: code/test  
Confidence: HIGH  

#### Summary
The Telegram cash command and cash management service call `brokerage._format_ticker()`, but the brokerage service has no such method in the current code.

#### Evidence
- `src/services/notification_service.py::_handle_cash` uses `brokerage._format_ticker(sweep_ticker)`.
- `src/services/cash_management_service.py::liquidate_sweep_asset` uses `brokerage_service._format_ticker(self.sweep_ticker)`.
- `git grep` found no `def _format_ticker` in `src`; tests that reference it monkeypatch the missing method.
- `tests/unit/test_cash_ticker_formatter.py::test_cash_command_uses_real_ticker_formatter` now proves `/cash` returns cash/sweep status without monkeypatching `_format_ticker`.
- `tests/unit/test_cash_ticker_formatter.py::test_cash_management_liquidate_uses_real_ticker_formatter` now proves cash sweep liquidation can locate the sweep ticker without monkeypatching `_format_ticker`.

#### Trigger
The operator invokes `/cash` or cash management attempts to locate the sweep ticker.

#### Broken assumption
Ticker normalization is assumed to exist on `BrokerageService`.

#### Financial or workflow consequence
The operator can lose visibility into cash and sweep-asset state, increasing manual debugging burden during liquidity or pause decisions.

#### Existing protection
The Telegram handler catches exceptions and replies with an error. `BrokerageService._format_ticker()` now provides a real shared formatter for cash command and cash-management lookups.

#### Missing protection
None for this formatter path after the 2026-05-11 fix.

#### Smallest safe fix
Implemented: add a small brokerage facade formatter that strips whitespace and uppercases ticker symbols.

#### Test required
Call `/cash` with a brokerage service that has no monkeypatched private method and assert it returns cash/sweep status rather than an error.

#### Validation command
`python -m pytest -q tests/unit/test_cash_ticker_formatter.py tests/test_telegram_commands.py tests/unit/test_brokerage_service_provider.py --asyncio-mode=auto`

#### Related issues
ISSUE-0016

#### Fix priority
P2

#### Notes
Fixed 2026-05-11 in `src/services/brokerage_service.py` by adding `BrokerageService._format_ticker()`. Regression tests added in `tests/unit/test_cash_ticker_formatter.py`. Validation passed: `python -m pytest -q tests/unit/test_cash_ticker_formatter.py tests/test_telegram_commands.py tests/unit/test_brokerage_service_provider.py --asyncio-mode=auto` with 11 passed. Remaining risk: this only normalizes symbols for current cash/sweep lookups; broader cash-command UX and sweep execution safety are not changed. Next recommended task was ISSUE-0010, then ISSUE-0013; after both 2026-05-12 fixes, continue with ISSUE-0014.

### ISSUE-0007 — Dashboard terminal auth smoke gate remains unresolved in readiness evidence

Status: FIXED  
Severity: HIGH  
Area: testing  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-09  
Evidence type: doc/test  
Confidence: HIGH  

#### Summary
Production readiness documents recorded a post-recovery integration smoke failure in the dashboard terminal command flow. The smoke helper assumed token-only login immediately returned `session_token`, but the current fail-closed auth flow returns a pending approval challenge first.

#### Evidence
- Before the fix, `tests/integration/test_terminal_bridge.py::dashboard_auth_query` read `response.json()["session_token"]` directly from the initial `/api/auth/login` response.
- Current `src/services/dashboard_service.py::_login` returns a pending challenge when no OTP is supplied, and `/api/auth/login/complete` returns the session after approval.
- `python -m pytest tests/integration/test_terminal_bridge.py::test_terminal_command_integration -q --asyncio-mode=auto` failed before the fix with `KeyError: 'session_token'`.
- The same command passed on 2026-05-09 after updating the smoke helper to complete the approval flow.
- `docs/soak-fault-injection-report.md` and `docs/production-scan-report.md` now record the passing terminal bridge rerun.

#### Trigger
Post-recovery smoke run or dashboard terminal command use after auth/session flow changes.

#### Broken assumption
The test assumed the first login response was a completed session instead of a fail-closed approval challenge.

#### Financial or workflow consequence
The operator terminal/control path may fail during degraded recovery, blocking manual commands when they matter most.

#### Existing protection
Integration test coverage exists for terminal bridge behavior. The smoke helper now follows the current two-step auth flow and stubs external notification/message sends at the test boundary.

#### Missing protection
None for this issue after the 2026-05-09 fix. Production approval still needs separate soak, active-market, and runtime-alert evidence.

#### Smallest safe fix
Update the terminal bridge smoke helper to complete the dashboard login challenge, rerun the narrow smoke test, and update readiness evidence.

#### Test required
The existing terminal bridge integration test should pass against current auth/session behavior.

#### Validation command
`python -m pytest tests/integration/test_terminal_bridge.py::test_terminal_command_integration -q --asyncio-mode=auto`

#### Related issues
ISSUE-0008, ISSUE-0016

#### Fix priority
P1

#### Notes
Fixed 2026-05-09 in `tests/integration/test_terminal_bridge.py` by keeping `TestClient` alive across the login/complete workflow, stubbing external notification/message sends, and completing `/api/auth/login/complete` before using `session_token`. Readiness docs updated in `docs/soak-fault-injection-report.md` and `docs/production-scan-report.md`. Validation passed: `python -m pytest tests/integration/test_terminal_bridge.py::test_terminal_command_integration tests/integration/test_terminal_bridge.py::test_terminal_approval_integration -q --asyncio-mode=auto`. Remaining risk: production approval is still blocked by ISSUE-0009 and the longer soak/active-market evidence gate; `tests/integration/test_terminal_bridge.py::test_audit_logging` still reaches real Postgres through `/exposure` and is not closed by this patch. Next recommended task is ISSUE-0009.

### ISSUE-0008 — Production approval lacks extended soak and active market evidence

Status: FIXED  
Severity: HIGH  
Area: deployment  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-08  
Evidence type: doc  
Confidence: HIGH  

#### Summary
The production gate is explicitly not approved. Existing evidence includes good focused tests and restart drills, but lacks the required 2-4 hour soak, clean log window, active market scan cycle, and resolved smoke failure.

#### Evidence
- `docs/production-scan-report.md` status is `NOT FULLY READY FOR PRODUCTION SIGN-OFF YET`.
- `docs/soak-fault-injection-report.md` status is `NOT APPROVED YET`.
- Required next actions include fixing/rerunning terminal smoke, longer soak, and confirming at least one active market scan cycle with non-zero pair processing.
- `scripts/run_production_soak_gate.py` now fails closed unless structured soak evidence proves the required duration, recovery drills, clean logs, smoke, no unresolved reconciliation rows, and active market scan.

#### Trigger
Any live or broker-connected paper run treated as production-ready based only on focused tests and short recovery drills.

#### Broken assumption
Unit/integration success is assumed to prove runtime dependency stability under realistic operation.

#### Financial or workflow consequence
The bot could trade while dependency recovery, dashboard command paths, and real scan behavior remain unproven, increasing the chance of workflow blockage or unmanaged state.

#### Existing protection
Readiness docs clearly block production sign-off, and the production soak gate now fails closed when evidence is missing or incomplete.

#### Missing protection
None for this approval-gate issue. Actual production approval is still blocked until a real evidence file satisfies the gate.

#### Smallest safe fix
Run the documented soak/fault-injection gate and update the report with pass/fail evidence.

#### Test required
An automated or scripted soak validation that asserts clean logs, healthy dependencies, passing smoke, and at least one active scan cycle.

#### Validation command
`python scripts/run_production_soak_gate.py --duration 2h --require-active-scan`

#### Related issues
ISSUE-0007, ISSUE-0009, ISSUE-0015

#### Fix priority
P0

#### Notes
This is a release gate, not a code defect. It remains P0 because it must be closed before broker-connected testing is trusted.

Fixed 2026-05-08 by adding `scripts/run_production_soak_gate.py` and `tests/unit/test_production_soak_gate.py`. The gate does not approve production by itself; it blocks approval unless the operator provides structured evidence for a paper-mode soak, recovery drills, clean logs, passing post-recovery smoke, zero unresolved reconciliation rows, and active scan cycles. Validation passed: `python -m pytest -q tests/unit/test_production_soak_gate.py tests/unit/test_validate_deploy_env.py tests/unit/test_backend_compose_secrets.py`.

### ISSUE-0009 — Runtime Postgres and gRPC transport faults lack an alert gate

Status: FIXED  
Severity: HIGH  
Area: observability  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-09  
Evidence type: log/test/doc  
Confidence: HIGH  

#### Summary
Production scan docs record repeated Postgres authentication failures and gRPC broken pipe/connection reset events. They may be historical or transient, but there is no documented alert threshold proving they are controlled.

#### Evidence
- `docs/production-readiness-plan.md` lists Postgres auth failures and execution-engine transient transport errors as risks to address.
- `docs/production-scan-report.md` observed repeated `password authentication failed for user "bot_admin"`, authentication timeouts, and gRPC broken pipe/connection reset events.
- The same docs recommend alerts for Postgres auth failure count and gRPC transport error rate.
- Before the fix, `scripts/run_production_soak_gate.py` accepted otherwise-complete evidence even when explicit Postgres/gRPC runtime error counts were non-zero.
- `tests/unit/test_runtime_alert_rules.py::test_postgres_and_grpc_error_spikes_fail_soak_gate` now proves non-zero Postgres auth and gRPC transport counts fail the soak gate.

#### Trigger
Credential drift, stale clients, dependency restarts, execution-engine reconnects, or network instability.

#### Broken assumption
Transport/auth noise is assumed benign without SLOs or alert thresholds.

#### Financial or workflow consequence
Persistence or execution sidecar instability can silently degrade audit writes, dashboard health, or order-path behavior until an operator notices late.

#### Existing protection
Docker health checks and readiness documentation exist. The production soak gate now requires structured `runtime_error_counts` with zero Postgres auth failures/timeouts and zero gRPC broken-pipe/connection-reset errors.

#### Missing protection
None for the production evidence gate after the 2026-05-09 fix. Live dashboard alerting for these classes is still a separate observability hardening task.

#### Smallest safe fix
Make the production soak gate fail when structured Postgres auth or gRPC transport error counts exceed the strict zero threshold.

#### Test required
Inject representative runtime error counts and assert the production soak gate fails.

#### Validation command
`python -m pytest tests/unit/test_runtime_alert_rules.py::test_postgres_and_grpc_error_spikes_fail_soak_gate -q`

#### Related issues
ISSUE-0008, ISSUE-0015

#### Fix priority
P1

#### Notes
Fixed 2026-05-09 in `scripts/run_production_soak_gate.py` by requiring structured zero counts for `postgres_auth_failures`, `postgres_auth_timeouts`, `grpc_broken_pipe_errors`, and `grpc_connection_reset_errors`. Regression test added: `tests/unit/test_runtime_alert_rules.py::test_postgres_and_grpc_error_spikes_fail_soak_gate`; existing soak-gate tests updated to include clean runtime counts. Validation passed: `python -m pytest -q tests/unit/test_runtime_alert_rules.py tests/unit/test_production_soak_gate.py tests/unit/test_validate_deploy_env.py tests/unit/test_backend_compose_secrets.py` with 7 passed. Remaining risk: this is a production evidence gate, not live alert delivery; broader API non-2xx/order reject/timeout/kill-switch alerting remains in the release checklist. Next recommended task is ISSUE-0011.

### ISSUE-0010 — Market session handling is suffix-based and ignores real exchange calendars

Status: FIXED  
Severity: MEDIUM  
Area: strategy  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-12  
Evidence type: code/test  
Confidence: HIGH  

#### Summary
Market-hours eligibility used ticker suffix heuristics and weekday windows rather than exchange calendars, holidays, or half days. Full-day holiday blocking has been added for the existing suffix venues, default US equities now close at 13:00 ET on common NYSE early-close dates, `.HK` symbols now use Hong Kong local trading hours plus noon early closes for common HKEX no-afternoon-session dates, `.L` symbols now close at 12:30 London time on common LSE half-days, `.DE` symbols now block common Xetra exchange closures not present in German public-holiday calendars, and `.AS`/`.PA` symbols now use local Euronext sessions plus common 14:05 CET half-day closes.

#### Evidence
- `src/monitor.py::get_market_config` maps suffixes such as `.HK`, `.DE`, `.AS`, `.PA`, and `.L` to fixed windows.
- `docs/tofix.md` states market calendar handling is approximate by venue suffix and needs exchange calendars and holidays.
- `src/monitor.py::is_market_open` now checks a maintained `holidays` calendar before accepting an equity market as open.
- `tests/unit/test_market_calendar.py::test_holiday_blocks_equity_scan_even_inside_suffix_window` proves a US equity is blocked on New Year's Day even during the normal weekday session window.
- `tests/unit/test_market_calendar.py::test_nyse_half_day_blocks_equity_scan_after_early_close` proves a US equity is blocked after the 13:00 ET NYSE early close on Friday, November 27, 2026.
- `tests/unit/test_market_calendar.py::test_hk_half_day_uses_local_session_and_blocks_afternoon` proves `.HK` symbols use the Hong Kong local morning session and block the afternoon on HKEX Christmas Eve 2026.
- `tests/unit/test_market_calendar.py::test_lse_half_day_blocks_equity_scan_after_early_close` proves `.L` symbols are blocked after the 12:30 London Stock Exchange Christmas Eve 2026 early close.
- `tests/unit/test_market_calendar.py::test_xetra_exchange_closure_blocks_equity_scan` proves `.DE` symbols are blocked on Xetra Christmas Eve 2026 when the fixed weekday/session window would otherwise allow trading.
- `tests/unit/test_market_calendar.py::test_euronext_half_day_blocks_scan_after_early_close` proves `.AS` and `.PA` symbols are blocked after the common 14:05 CET Euronext cash-market half-day close.

#### Trigger
Exchange holidays, half-days, daylight-saving boundary changes, regional market closures, or cross-listed symbols with misleading suffixes.

#### Broken assumption
Ticker suffix and weekday fixed windows are enough to know when data and orders are valid.

#### Financial or workflow consequence
The bot can scan or trade on stale data outside real sessions, or skip valid trading windows, degrading signals and exits.

#### Existing protection
Crypto pairs are treated as 24/7 and equity pairs have a basic session-overlap gate. Full-day holidays now close default US equities via the NYSE financial calendar and suffix venues via country holiday calendars. Default US equities now also use a small NYSE early-close table for recurring 13:00 ET half-days. `.HK` symbols now use 09:30-16:00 HKT and a noon close for common HKEX half-days. `.L` symbols now close at 12:30 London time on common LSE half-days. `.DE` symbols now block Xetra Christmas Eve and New Year's Eve closures. `.AS` and `.PA` now use local Amsterdam/Paris sessions and a 14:05 CET close on common Euronext half-days.

#### Missing protection
No maintained exchange-calendar provider is used for ad-hoc future exchange notices. Current configured venue coverage is protected by focused regression tests, but operators should still watch official exchange calendars before live trading.

#### Smallest safe fix
Implemented the smallest safe mitigations for full-day holidays, default US half-days, HKEX `.HK` half-days/local session times, LSE `.L` common half-days, Xetra `.DE` Christmas/New Year's Eve closures, and Euronext `.AS`/`.PA` local session plus common half-day handling without changing order behavior.

#### Test required
Added US full-day holiday, NYSE half-day, HKEX half-day/local-session, LSE half-day, Xetra closure, and Euronext `.AS`/`.PA` half-day regression tests.

#### Validation command
`python -m pytest tests/unit/test_market_calendar.py -q`

#### Related issues
ISSUE-0003

#### Fix priority
P2

#### Notes
This is medium because other guards may still reject trades, but it undermines data freshness assumptions.

Partial mitigation 2026-05-12: `src/monitor.py` now uses `holidays.financial_holidays("NYSE")` for default US equities and `holidays.country_holidays()` for HK/DE/NL/FR/PT/GB suffix venues. Validation passed: `python -m pytest tests/unit/test_market_calendar.py::test_holiday_blocks_equity_scan_even_inside_suffix_window -q`. Broader validation remains blocked by unrelated pre-existing failures in async pair-eligibility tests and full-suite collection imports.

Partial mitigation 2026-05-12: `src/monitor.py::_market_early_close_time` now shortens default US equity sessions to 13:00 ET on recurring NYSE early-close dates, including the day after Thanksgiving. Regression test added: `tests/unit/test_market_calendar.py::test_nyse_half_day_blocks_equity_scan_after_early_close`. Validation passed: `python -m pytest tests/unit/test_market_calendar.py -q` with 2 passed. Full-suite validation remains blocked by unrelated collection errors in `tests/benchmark/test_value_traps.py` and `tests/unit/test_whale_watcher.py`.

Partial mitigation 2026-05-12: `src/monitor.py::get_market_config` now uses Hong Kong local hours for `.HK` symbols, and `_market_early_close_time` returns a noon HKT close for HKEX Christmas Eve, New Year's Eve, and Lunar New Year eve cases. Regression test added: `tests/unit/test_market_calendar.py::test_hk_half_day_uses_local_session_and_blocks_afternoon`. Validation passed: `python -m pytest tests/unit/test_market_calendar.py -q` with 3 passed. Full-suite validation remains blocked by unrelated collection errors in `tests/benchmark/test_value_traps.py` and `tests/unit/test_whale_watcher.py`.

Partial mitigation 2026-05-12: `src/monitor.py::_market_early_close_time` now returns a 12:30 London close for `.L`/GB symbols on Christmas Eve and New Year's Eve. Regression test added: `tests/unit/test_market_calendar.py::test_lse_half_day_blocks_equity_scan_after_early_close`. Validation passed: `python -m pytest tests/unit/test_market_calendar.py -q` with 4 passed. Full-suite validation remains blocked by unrelated collection errors in `tests/benchmark/test_value_traps.py` and `tests/unit/test_whale_watcher.py`.

Partial mitigation 2026-05-12: `src/monitor.py::_is_market_holiday` now treats `.DE`/Xetra Christmas Eve and New Year's Eve as closed exchange days before falling back to German public holidays. Regression test added: `tests/unit/test_market_calendar.py::test_xetra_exchange_closure_blocks_equity_scan`. Validation passed: `python -m pytest tests/unit/test_market_calendar.py -q` with 5 passed. Full-suite validation remains blocked by unrelated collection errors in `tests/benchmark/test_value_traps.py` and `tests/unit/test_whale_watcher.py`.

Fixed 2026-05-12 for scoped configured calendar coverage: `.AS` now uses `Europe/Amsterdam`, `.PA` now uses `Europe/Paris`, both use 09:00-17:30 local sessions, and `_market_early_close_time()` applies a 14:05 local close for common Euronext Amsterdam/Paris half-days on December 24 and December 31. Regression test updated: `tests/unit/test_market_calendar.py::test_euronext_half_day_blocks_scan_after_early_close`. Validation passed: `python -m pytest tests/unit/test_market_calendar.py -q` with 6 passed. Full-suite validation remains blocked by unrelated collection errors in `tests/benchmark/test_value_traps.py` and `tests/unit/test_whale_watcher.py`.

### ISSUE-0011 — Corporate actions do not invalidate pair and Kalman state

Status: FIXED  
Severity: HIGH  
Area: strategy  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-09  
Evidence type: code/test  
Confidence: HIGH  

#### Summary
Kalman state can warm-start from Redis without a version or invalidation key tied to splits, symbol changes, special dividends, or pair definition changes.

#### Evidence
- `src/services/arbitrage_service.py::get_or_create_filter` reloads saved Kalman state from Redis by `pair_id`.
- `src/services/redis_service.py::save_kalman_state` stores `x`, `P`, `z_score`, and `innovation_variance`, but no corporate-action version or data-adjustment fingerprint.
- `docs/tofix.md` says corporate actions are not a complete first-class invalidation path.
- Before the fix, `tests/unit/test_arbitrage_state_invalidation.py::test_kalman_state_invalidates_on_corporate_action` failed because a Redis state with `state_fingerprint="old-adjusted-history"` was warm-started against changed adjusted history.
- `src/services/arbitrage_service.py::build_state_fingerprint` now fingerprints the pair id plus the adjusted history payload used for pre-warming.
- `src/services/redis_service.py::save_kalman_state` now stores `state_fingerprint`, and `get_kalman_state` returns it for warm-start validation.

#### Trigger
Split, symbol change, special dividend, adjusted-history change, or pair remap after Kalman state already exists in Redis.

#### Broken assumption
Saved Kalman state remains valid as long as the pair id string is unchanged.

#### Financial or workflow consequence
Hedge ratio, z-score, and spread state can be stale or structurally wrong, causing corrupted entry/exit decisions.

#### Existing protection
Many historical data paths use adjusted series, rolling cointegration checks exist, and saved Kalman state now carries a data-adjustment fingerprint.

#### Missing protection
None for the saved Kalman warm-start path after the 2026-05-09 fix. A dedicated corporate-action provider/event pipeline is still not implemented.

#### Smallest safe fix
Store a state fingerprint with Kalman state and force re-warm when adjusted-history data no longer matches the saved fingerprint.

#### Test required
Seed Redis Kalman state, simulate an adjusted-history fingerprint change, and assert the filter is not warm-started from stale state.

#### Validation command
`python -m pytest tests/unit/test_arbitrage_state_invalidation.py::test_kalman_state_invalidates_on_corporate_action -q`

#### Related issues
ISSUE-0010, ISSUE-0012

#### Fix priority
P1

#### Notes
Fixed 2026-05-09 in `src/services/arbitrage_service.py` and `src/services/redis_service.py` by storing a `history-v1` state fingerprint and ignoring saved Redis Kalman state when current prewarm history produces a different fingerprint. Regression test added: `tests/unit/test_arbitrage_state_invalidation.py::test_kalman_state_invalidates_on_corporate_action`. Validation passed: `python -m pytest -q tests/unit/test_arbitrage_state_invalidation.py tests/unit/test_arbitrage_math.py tests/unit/test_kalman.py tests/unit/test_kalman_q_inflation.py tests/unit/test_rolling_cointegration.py` with 20 passed. Remaining risk: this detects adjusted-history changes seen during prewarm/reload; it does not add a full corporate-action event provider. Next recommended task is ISSUE-0018.

### ISSUE-0012 — SEC/fundamental cache misses default to neutral in live signal path

Status: FIXED  
Severity: HIGH  
Area: strategy  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-09  
Evidence type: code/test  
Confidence: HIGH  

#### Summary
When Redis has no fundamental score for a ticker, the orchestrator logs a critical cache miss but uses the configured default score. If the default is above the veto threshold, structurally unknown names can proceed.

#### Evidence
- `src/agents/orchestrator.py::ainvoke` calls `redis_service.get_fundamental_score()` for both tickers.
- On missing score, it logs `CRITICAL - Fundamental cache miss` and sets `score_a`/`score_b` to `settings.ORCH_FUNDAMENTAL_DEFAULT_SCORE`.
- Veto only happens when score is below `settings.ORCH_FUNDAMENTAL_VETO_SCORE`.
- `docs/tofix.md` records that SEC/fundamental cache misses default to neutral.
- `tests/unit/test_orchestrator_fundamentals.py::test_live_mode_vetoes_missing_fundamental_score` now proves a live-mode missing score vetoes the signal instead of using the neutral default.

#### Trigger
SEC worker lag, Redis expiry, new symbols, cache flush, or provider failure.

#### Broken assumption
A missing fundamental score is safe enough to represent as the neutral default.

#### Financial or workflow consequence
The bot can accept signals for companies whose structural/fundamental risk is unknown, corrupting trading decisions while telemetry only warns.

#### Existing protection
The miss is logged and broadcast via telemetry. Live or `LIVE_CAPITAL_DANGER` mode now records a fundamental veto and blocks the signal when any ticker has unknown fundamental state.

#### Missing protection
Stale-but-present cache entries still do not have a maximum age check.

#### Smallest safe fix
Implemented for missing Redis scores and Redis read failures: in live or broker-connected mode, treat unknown SEC scores as a veto with an explicit unknown-fundamentals reason.

#### Test required
Simulate missing Redis score in live mode and assert the orchestrator vetoes or returns a blocked decision.

#### Validation command
`python -m pytest tests/unit/test_orchestrator_fundamentals.py::test_live_mode_vetoes_missing_fundamental_score -q`

#### Related issues
ISSUE-0011, ISSUE-0013

#### Fix priority
P1

#### Notes
Fixed 2026-05-09 in `src/agents/orchestrator.py` by tracking unknown fundamental tickers and vetoing live or `LIVE_CAPITAL_DANGER` entries before portfolio weighting. Regression test added: `tests/unit/test_orchestrator_fundamentals.py::test_live_mode_vetoes_missing_fundamental_score`. Validation passed: `python -m pytest -q tests/unit/test_orchestrator_fundamentals.py tests/unit/test_orchestrator_mab.py tests/unit/test_sector_leader_regime.py::test_orchestrator_sector_veto tests/unit/test_sector_leader_regime.py::test_orchestrator_missing_sector_defaults_to_spy` with 4 passed. Remaining risk: stale-but-present fundamental cache entries still need an age/freshness guard. Next recommended task is ISSUE-0018.

### ISSUE-0013 — Whale watcher is configured and documented but currently always neutral

Status: FIXED  
Severity: MEDIUM  
Area: strategy  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-12  
Evidence type: code/test/doc  
Confidence: HIGH  

#### Summary
The system described whale-watcher context and configuration as active protection, but the active agent implementation was a dummy that always returned neutral. The active runtime now reports the whale watcher as inactive/legacy-neutral instead of presenting it as active neutral protection.

#### Evidence
- Before the fix, `src/agents/whale_watcher_agent.py::evaluate` returned `self.neutral("Whale watcher agent is in legacy mode.")` without inactive status fields.
- Before the fix, `src/config.py` defaulted `WHALE_WATCHER_ENABLED` to `True` even though no active evaluator existed.
- Before the fix, `docs/STRATEGY.md` described whale watcher context and vetoes without saying the active implementation was inactive.
- `tests/unit/test_whale_watcher.py` now asserts the legacy whale watcher status, agent verdict, and orchestrator telemetry all report `inactive`/`INACTIVE`.

#### Trigger
Any signal where whale/exchange-flow context is expected to adjust confidence or veto risk.

#### Broken assumption
Configured whale watcher controls imply active signal protection.

#### Financial or workflow consequence
Signals proceed without the documented whale-flow veto, and operators may overestimate the amount of active risk filtering.

#### Existing protection
The dummy is neutral rather than unstable, so it does not introduce random vetoes. It now reports `active=False`, `status=inactive`, and `mode=legacy_neutral`; orchestrator telemetry emits the whale watcher verdict as `INACTIVE`.

#### Missing protection
No restored cache-backed whale-flow evaluator or stale-cache health checks. The current protection is disclosure, not whale-flow risk analysis.

#### Smallest safe fix
Implemented: mark the whale watcher as inactive/legacy in agent status, orchestrator telemetry, config defaults, and strategy docs.

#### Test required
Added `tests/unit/test_whale_watcher.py` coverage for inactive agent status, inactive evaluate output, and orchestrator `INACTIVE` telemetry.

#### Validation command
`python -m pytest tests/unit/test_whale_watcher.py -q`

#### Related issues
ISSUE-0012

#### Fix priority
P2

#### Notes
This is classified medium because it removes a documented protection rather than directly breaking execution.

Fixed 2026-05-12 in `src/agents/whale_watcher_agent.py`, `src/agents/orchestrator.py`, `src/config.py`, `frontend/src/services/api.ts`, `frontend/src/components/ThoughtJournal.tsx`, `docs/STRATEGY.md`, and `docs/tofix.md` by making the active whale watcher explicitly inactive instead of silently neutral. Regression tests updated in `tests/unit/test_whale_watcher.py`. Validation passed: `python -m pytest tests/unit/test_whale_watcher.py -q` with 3 passed and `python -m pytest -q tests/unit/test_whale_watcher.py tests/unit/test_orchestrator_fundamentals.py tests/unit/test_orchestrator_mab.py tests/unit/test_sector_leader_regime.py::test_orchestrator_sector_veto tests/unit/test_sector_leader_regime.py::test_orchestrator_missing_sector_defaults_to_spy` with 7 passed. Full-suite validation now proceeds past whale watcher collection but remains blocked by unrelated `tests/benchmark/test_value_traps.py` importing missing `fundamental_analyst`.

### ISSUE-0014 — Local runtime dependency path differs from CI and Docker

Status: FIXED
Severity: MEDIUM  
Area: deployment  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-13
Evidence type: config/doc/test
Confidence: HIGH  

#### Summary
Local setup docs previously installed from `requirements.txt`, while CI and Docker install from `requirements.lock` on Python 3.11. This could make local tests pass or fail against a different dependency graph than deployed services.

#### Evidence
- Before the fix, `README.md` and `docs/OPERATIONS.md` instructed `pip install -r requirements.txt`.
- `.github/workflows/deploy.yml` installs `requirements.lock` with `uv`.
- `infra/Dockerfile` installs `requirements.lock` on `python:3.11-slim`.
- Before the fix, README described Python `3.10+`.
- `tests/unit/test_docs_runtime_parity.py::test_local_setup_uses_locked_requirements` failed before the docs change and now verifies README/operations docs use `uv pip install -r requirements.lock` and Python 3.11.

#### Trigger
Developer installs locally from loose requirements, dependency resolver selects newer packages, or a Python version differs from the Docker/CI runtime.

#### Broken assumption
Any Python 3.10+ environment with `requirements.txt` is equivalent to the deployed locked Python 3.11 environment.

#### Financial or workflow consequence
Tests can pass locally while deployment breaks, or local audit evidence can fail to reproduce production behavior.

#### Existing protection
CI and Docker use `requirements.lock`. README and `docs/OPERATIONS.md` now steer local setup to Python 3.11 and `uv pip install -r requirements.lock`.

#### Missing protection
None for this scoped docs-parity issue after the 2026-05-13 fix.

#### Smallest safe fix
Implemented: update local setup docs to use the lockfile and Python 3.11.

#### Test required
Added `tests/unit/test_docs_runtime_parity.py::test_local_setup_uses_locked_requirements`.

#### Validation command
`python -m pytest tests/unit/test_docs_runtime_parity.py::test_local_setup_uses_locked_requirements -q`

#### Related issues
ISSUE-0005, ISSUE-0015

#### Fix priority
P2

#### Notes
Fixed 2026-05-13 in `README.md`, `docs/OPERATIONS.md`, and `tests/unit/test_docs_runtime_parity.py`. Validation passed: `python -m pytest tests/unit/test_docs_runtime_parity.py::test_local_setup_uses_locked_requirements -q`. Remaining risk: this patch proves docs/runtime parity only; broader CI coverage gaps remain ISSUE-0015. Next recommended task is ISSUE-0015.

### ISSUE-0015 — CI gates miss broker failure contracts and long-running safety scenarios

Status: FIXED
Severity: MEDIUM  
Area: testing  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-13
Evidence type: config/test
Confidence: HIGH  

#### Summary
CI runs meaningful unit/integration/Java/frontend quality checks. Before the fix, the highest-risk broker/execution safety contracts were only implicit in the broad unit suite and were not represented as an explicit fail-fast safety gate.

#### Evidence
- `.github/workflows/deploy.yml` runs Python unit tests, Python integration tests, Java tests/build, and frontend lint/build/test when relevant paths change.
- `docs/tofix.md` calls for live-path contract tests with fake T212/Alpaca/Web3 providers and Java gRPC health/status tests.
- `docs/production-readiness-plan.md` and `docs/soak-fault-injection-report.md` require soak/fault-injection gates outside the current CI quality jobs.
- ISSUE-0004 now has focused budget mutation regression tests; remaining CI gaps are broader broker failure contracts and long-running safety scenarios.
- `tests/unit/test_ci_safety_gates.py::test_deploy_workflow_runs_broker_execution_safety_contracts` failed before the workflow change and now proves the deploy workflow has an explicit broker/execution safety contract step.
- `.github/workflows/deploy.yml` now runs focused Alpaca timeout/read-failure, monitor ambiguity/partial-fill/close, startup guard, paper wallet, production soak-gate, runtime alert, and broker-route config tests before the broad unit suite.
- `.github/workflows/deploy.yml` now treats workflow edits as Python-quality changes so the CI guard test runs when the gate itself changes.

#### Trigger
PRs or deployments that pass existing quality lanes but change broker, execution, or runtime safety behavior.

#### Broken assumption
The existing CI quality lanes are assumed to cover all safety-critical trading contracts.

#### Financial or workflow consequence
Live-breaking execution and reconciliation gaps can pass CI and reach deployment.

#### Existing protection
CI has path-filtered Python, Java, and frontend quality jobs. The Python quality lane now includes an explicit broker/execution safety contract step before the broad unit suite.

#### Missing protection
None for this scoped CI safety-contract gate after the 2026-05-13 fix. Real long soak execution remains an operator evidence gate, not a CI runtime job.

#### Smallest safe fix
Implemented: add a focused broker/execution safety contract step to CI and a workflow lint test that keeps it present.

#### Test required
Added `tests/unit/test_ci_safety_gates.py::test_deploy_workflow_runs_broker_execution_safety_contracts`.

#### Validation command
`python -m pytest tests/unit/test_ci_safety_gates.py::test_deploy_workflow_runs_broker_execution_safety_contracts -q`

#### Related issues
ISSUE-0001, ISSUE-0002, ISSUE-0003, ISSUE-0004, ISSUE-0008, ISSUE-0009

#### Fix priority
P2

#### Notes
Fixed 2026-05-13 in `.github/workflows/deploy.yml` and `tests/unit/test_ci_safety_gates.py`. Regression test added: `tests/unit/test_ci_safety_gates.py::test_deploy_workflow_runs_broker_execution_safety_contracts`. Validation passed: `python -m pytest tests/unit/test_ci_safety_gates.py::test_deploy_workflow_runs_broker_execution_safety_contracts -q` and the CI safety command with 45 passed. Remaining risk: CI still does not execute a real multi-hour soak; it only validates the soak evidence gate and alert-threshold tests. Next recommended task is ISSUE-0017.

### ISSUE-0016 — Dashboard bot status mirrors desired state instead of unsafe operational state

Status: FIXED  
Severity: HIGH  
Area: frontend  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-11  
Evidence type: code/test  
Confidence: HIGH  

#### Summary
Dashboard summary reports `bot_status` from the desired dashboard state. Startup fail-fast can set persistence `operational_status` to `PAUSED_REQUIRES_MANUAL_REVIEW` and return before the main loop, but no dashboard update is visible in that fail-fast path.

#### Evidence
- `src/services/dashboard_service.py::build_summary` sets `"bot_status": dashboard_state.desired_bot_state`.
- `src/services/dashboard_service.py::DashboardState` initializes `desired_bot_state = "RUNNING"`.
- `src/monitor.py::_fail_fast_on_unresolved_execution_state` marks unresolved state and sends notification, then `run()` returns if it fails.
- The dashboard update calls in `src/monitor.py::run` occur before and after this path, but the fail-fast helper itself does not update dashboard status to manual review.
- `tests/unit/test_dashboard_status.py::test_summary_reports_manual_review_after_startup_fail_fast` now proves summary status follows persisted manual-review state instead of desired state.
- `tests/unit/test_startup_guards.py::test_startup_blocks_when_unresolved_execution_state_exists` now proves startup fail-fast pushes `PAUSED_REQUIRES_MANUAL_REVIEW` to dashboard state.

#### Trigger
Startup finds unresolved execution state such as `CLOSING`, `CLOSE_FAILED`, or manual reconciliation rows.

#### Broken assumption
Desired operator state is equivalent to actual safe runtime state.

#### Financial or workflow consequence
The dashboard can show a running/desired state while the bot is paused for manual reconciliation, hiding blocked workflows or unsafe unknown broker state from the operator.

#### Existing protection
Persistence status and Telegram notification record the unsafe state. Dashboard summary now returns `operational_status`, `desired_bot_state`, and `blocked`, and `bot_status` uses non-normal persisted operational state before desired state. Startup fail-fast now updates dashboard stage to `PAUSED_REQUIRES_MANUAL_REVIEW`.

#### Missing protection
None for the startup manual-review summary path after the 2026-05-09 fix.

#### Smallest safe fix
Implemented: include persisted operational status in dashboard summary, have unsafe operational status override displayed bot status, prefer summary status in the React shell, and update dashboard stage during fail-fast startup.

#### Test required
Simulate unresolved startup state and assert `/api/summary` reports manual review/blocked rather than `RUNNING`.

#### Validation command
`python -m pytest tests/unit/test_dashboard_status.py::test_summary_reports_manual_review_after_startup_fail_fast -q`

#### Related issues
ISSUE-0001, ISSUE-0007

#### Fix priority
P1

#### Notes
Fixed 2026-05-11 in `src/services/dashboard_service.py`, `src/monitor.py`, and `frontend/src/App.tsx`. Regression tests added/updated: `tests/unit/test_dashboard_status.py::test_summary_reports_manual_review_after_startup_fail_fast` and `tests/unit/test_startup_guards.py::test_startup_blocks_when_unresolved_execution_state_exists`. Validation passed: `python -m pytest -q tests/unit/test_dashboard_status.py tests/unit/test_dashboard_config.py tests/unit/test_dashboard_sessions.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_startup_guards.py` with 19 passed, and `node node_modules/typescript/bin/tsc -b` from `frontend/`. Remaining risk: frontend lint still has pre-existing unrelated failures in `LoginView.test.tsx` and `useStartupProgress.ts`. Next recommended task is ISSUE-0018.

### ISSUE-0017 — Fire-and-forget background tasks lack a watchdog

Status: FIXED
Severity: MEDIUM  
Area: orchestration  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-13
Evidence type: code/test
Confidence: HIGH  

#### Summary
Several background workflows were launched with `asyncio.create_task()` without retained task handles, restart policy, or a central dead-letter/health surface.

#### Evidence
- `src/monitor.py::run` starts `_auto_scout_and_rotate_loop()` with `asyncio.create_task()`.
- `src/monitor.py::run` starts `_recheck_cointegration(pair)` tasks during scanning.
- `src/services/persistence_service.py::close_trade` triggers reflection in the background after ledger closure.
- `tests/unit/test_background_task_watchdog.py::test_background_task_failure_surfaces_in_health` failed before the fix because no watchdog module or health surface existed.
- `src/services/background_task_watchdog.py` now records active task handles, completions, and exceptions.
- `src/services/dashboard_service.py::health_snapshot` now exposes `background_tasks` and reports `status=degraded` when a tracked background task fails.

#### Trigger
Unhandled exception, cancellation, event-loop shutdown, or dependency failure inside a background task.

#### Broken assumption
Background tasks either never fail or log enough for operators to notice.

#### Financial or workflow consequence
Scouting, cointegration refresh, or reflection can stop silently, degrading decisions and recovery evidence.

#### Existing protection
Some task bodies catch/log local exceptions. Background tasks created by monitor, dashboard, and close-reflection paths are now tracked by `background_task_watchdog`.

#### Missing protection
None for this scoped exception-surfacing issue after the 2026-05-13 fix. Automatic restart and durable dead-letter queues remain out of scope.

#### Smallest safe fix
Implemented: wrap background task creation in a small tracked-task helper that records completion/exceptions and exposes health.

#### Test required
Added `tests/unit/test_background_task_watchdog.py::test_background_task_failure_surfaces_in_health`.

#### Validation command
`python -m pytest tests/unit/test_background_task_watchdog.py::test_background_task_failure_surfaces_in_health -q`

#### Related issues
ISSUE-0009, ISSUE-0016

#### Fix priority
P2

#### Notes
Fixed 2026-05-13 in `src/services/background_task_watchdog.py`, `src/monitor.py`, `src/services/persistence_service.py`, and `src/services/dashboard_service.py`. Regression test added: `tests/unit/test_background_task_watchdog.py::test_background_task_failure_surfaces_in_health`. Validation passed: `python -m pytest tests/unit/test_background_task_watchdog.py -q` and adjacent dashboard/startup checks. Remaining risk: watchdog records and surfaces failures but does not restart failed tasks or persist a durable dead-letter queue. Next recommended task is ISSUE-0019.

### ISSUE-0018 — Dashboard wallet buy proceeds despite cash-limited planning

Status: FIXED  
Severity: HIGH  
Area: risk  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-11  
Evidence type: code/test  
Confidence: HIGH  

#### Summary
The dashboard wallet recommendation buy path detects `cash_limited=true` but proceeds to place orders using the requested budget, logging only a warning that it is deferring to the broker.

#### Evidence
- `src/services/dashboard_service.py::calculate_wallet_recommendations` sets `cash_limited` when requested budget exceeds effective broker cash.
- `src/services/dashboard_service.py::buy_wallet_recommendations` logs `Proceeding with wallet recommendation BUY despite cash_limited=true`.
- The same method continues to build allocations and call the order placement path.
- `tests/unit/test_dashboard_wallet_sync.py::test_wallet_buy_blocks_when_cash_limited` now proves a cash-limited wallet buy is blocked before broker order placement.

#### Trigger
Operator requests a wallet recommendation buy budget greater than effective broker cash.

#### Broken assumption
Broker rejection is an acceptable last-line budget control for dashboard-initiated wallet buys.

#### Financial or workflow consequence
Orders can fail mid-batch, create confusing partial allocation, or bypass the dashboard's own risk signal.

#### Existing protection
The plan exposes `cash_limited`, and broker/API checks may reject orders. `buy_wallet_recommendations()` now raises `HTTPException(400)` before planning or order placement when `cash_limited=true`.

#### Missing protection
None for this cash-limited wallet-buy path after the 2026-05-11 fix.

#### Smallest safe fix
Implemented: block buy by default when `cash_limited=true` and return an explicit response reason.

#### Test required
Mock effective cash below requested budget and assert no live broker orders are placed unless an explicit override is present.

#### Validation command
`python -m pytest tests/unit/test_dashboard_wallet_sync.py::test_wallet_buy_blocks_when_cash_limited -q`

#### Related issues
ISSUE-0004, ISSUE-0016

#### Fix priority
P1

#### Notes
Fixed 2026-05-11 in `src/services/dashboard_service.py` by rejecting wallet recommendation buys when requested budget exceeds effective broker cash. Regression test added: `tests/unit/test_dashboard_wallet_sync.py::test_wallet_buy_blocks_when_cash_limited`. Validation passed: `python -m pytest -q tests/unit/test_dashboard_wallet_sync.py tests/unit/test_dashboard_wallet_new_methods.py tests/unit/test_dashboard_config.py tests/unit/test_dashboard_status.py` with 12 passed. Remaining risk: no explicit operator override/cap flow exists; cash-limited buys now fail closed. Next recommended task is ISSUE-0006 after ISSUE-0023 was fixed.

### ISSUE-0019 — Closing trades overwrites per-leg metadata

Status: OPEN  
Severity: MEDIUM  
Area: persistence  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-08  
Evidence type: code  
Confidence: HIGH  

#### Summary
`close_trade()` updates every ledger row for a signal with a new `metadata_json` containing only exit prices, pnl, and exit reason. This overwrites entry metadata such as broker order ids, client order ids, and leg execution details.

#### Evidence
- `src/services/persistence_service.py::close_trade` runs `update(TradeLedger).where(TradeLedger.signal_id == signal_id).values(metadata_json={"exit_prices": ..., "pnl": ..., "exit_reason": ...})`.
- Entry rows written by `src/monitor.py::execute_trade` include metadata such as broker order ids and execution context.
- Later analytics read PnL from metadata, creating incentive to keep writing close metadata into the same field.

#### Trigger
Any successful close via `persistence_service.close_trade()`.

#### Broken assumption
Close metadata can replace entry metadata without losing audit-critical information.

#### Financial or workflow consequence
Post-close broker reconciliation and forensic audit lose the exact order identifiers needed to explain fills, slippage, or disputes.

#### Existing protection
The trade rows themselves retain ticker, side, quantity, price, and timestamps.

#### Missing protection
No metadata merge, separate close metadata field, fill-event table, or immutable event log for order lifecycle.

#### Smallest safe fix
Merge close metadata into existing metadata instead of replacing it, or store close details in a dedicated field/table.

#### Test required
Create a ledger row with entry broker metadata, close it, and assert entry metadata remains while close metadata is added.

#### Validation command
`python -m pytest tests/unit/test_persistence_service.py::test_close_trade_preserves_entry_metadata -q`

#### Related issues
ISSUE-0001, ISSUE-0002

#### Fix priority
P2

#### Notes
This is especially important while investigating partial exposure and emergency-close cases.

### ISSUE-0020 — Brain ledgers mix historical notes, closed invariants, and open production gates

Status: OPEN  
Severity: LOW  
Area: documentation  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-08  
Evidence type: doc  
Confidence: HIGH  

#### Summary
The existing brain contains valuable audit notes, but issues were spread across historical prose, old P0 labels, closed invariant notes, and production-readiness summaries without a single canonical `ISSUE-XXXX` register.

#### Evidence
- `.brain/04_AUDIT_LEDGER.md` contains current audition context, historical dirty-worktree notes, and fixed invariant tables.
- `.brain/05_BUG_LEDGER.md` mixes closed/protected items, old `P0-XXX`/`P1-XXX` IDs, and open production gates.
- Several known risks in docs were not in the exact issue format requested by the current audit.

#### Trigger
Future audits search for known risks and encounter multiple naming schemes or closed/open state mixed together.

#### Broken assumption
Historical audit notes are enough to prevent duplicate issue discovery.

#### Financial or workflow consequence
The team can waste audit time rediscovering known issues or accidentally treat historical closed invariants as broad production approval.

#### Existing protection
The brain folder exists and contains useful release, testing, and workflow context.

#### Missing protection
Canonical open issue IDs, subsystem problem map, priority queue, untested-risk list, and workflow failure map.

#### Smallest safe fix
Maintain the canonical `ISSUE-XXXX` register and generated maps added by this audit; move future findings into those IDs.

#### Test required
Documentation review: every open issue in priority/problem maps must point to one canonical issue entry.

#### Validation command
`python scripts/validate_brain_issue_links.py`

#### Related issues
None

#### Fix priority
P3

#### Notes
This audit starts the canonical structure but does not delete historical notes.

### ISSUE-0021 — Leg A full-fill gate accepts short `status=filled` quantity

Status: FIXED  
Severity: CRITICAL  
Area: execution  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-08  
Evidence type: code  
Confidence: HIGH  

#### Summary
`execute_trade()` blocks Leg B for explicit `partially_filled` Leg A snapshots, but a broker snapshot with `status="filled"` and a positive `filled_qty` below the requested Leg A quantity is treated as a full fill. That lets Leg B submit against a hedge size calculated from the requested Leg A quantity, not the actual filled quantity.

#### Evidence
- `src/monitor.py::execute_trade` sets `status_a = OrderStatus.LEG_A_FILLED` when `status_raw_a == "filled" and filled_qty_a > 0`.
- The same function has `size_a = legs.quantity_a`, but it never compares `filled_qty_a` to `size_a` before `await self.brokerage.place_value_order(... client_order_id=f"{signal_id}-B")`.
- `tests/unit/test_monitor.py::test_execute_trade_blocks_leg_b_without_confirmed_leg_a_fill` covers explicit `partially_filled` and zero-fill snapshots, but not `status="filled"` with a short quantity.
- `src/monitor.py::_close_position` now compares close filled quantity with expected quantity, proving the safer invariant is local and concrete.

#### Trigger
Leg A is submitted and the broker returns an order snapshot with `status="filled"` but `filled_qty` less than the requested Leg A quantity, for example because of rounding, notional sizing, broker adjustment, or partial execution represented inconsistently.

#### Broken assumption
The code assumes broker `status="filled"` plus any positive quantity proves the requested Leg A quantity filled completely.

#### Financial or workflow consequence
Leg B can be sized for a larger hedge than the actual Leg A fill, creating inverted or over-hedged exposure. This can duplicate exposure, distort risk, and make the ledger claim a fully opened pair that does not match broker reality.

#### Existing protection
Explicit `partially_filled`, rejected, canceled, expired, zero-fill, unknown, and missing Leg A snapshots block Leg B.

#### Missing protection
No quantity-completeness comparison between `filled_qty_a` and the requested `size_a` before placing Leg B.

#### Smallest safe fix
Require `filled_qty_a` to be at least the requested `size_a` within a small tolerance before marking Leg A `LEG_A_FILLED`; otherwise mark partial/manual reconciliation and do not place Leg B.

#### Test required
Simulate Leg A snapshot `{"status": "filled", "filled_qty": size_a / 2}` and assert Leg B is not submitted, the signal is marked `PARTIAL_EXPOSURE`, and the operator is notified.

#### Validation command
`python -m pytest tests/unit/test_monitor.py::test_execute_trade_blocks_leg_b_when_leg_a_filled_quantity_is_short -q --asyncio-mode=auto`

#### Related issues
ISSUE-0001, ISSUE-0002, ISSUE-0022

#### Fix priority
P0

#### Notes
This is a stronger, more precise form of the partial-fill risk already described in P1-002. It should be fixed before broker-connected testing because the bad branch occurs before the second live order.

Fixed 2026-05-08 in `src/monitor.py::execute_trade` by requiring `filled_qty_a` to cover requested `size_a` before Leg B is submitted. Regression test added: `tests/unit/test_monitor.py::test_execute_trade_blocks_leg_b_when_leg_a_filled_quantity_is_short`. Validation passed: `python -m pytest tests/unit/test_monitor.py -q --asyncio-mode=auto`.

### ISSUE-0022 — Leg B terminal rejection after submit does not emergency-close Leg A

Status: FIXED  
Severity: CRITICAL  
Area: execution  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-08  
Evidence type: code  
Confidence: HIGH  

#### Summary
The monitor attempts emergency close only when the initial Leg B placement response is `status="error"`. If Leg B placement is accepted but later fill polling returns `rejected`, `canceled`, `cancelled`, or `expired`, the code records partial exposure but does not emergency-close Leg A and then logs a misleading `TRADE EXECUTED` message.

#### Evidence
- `src/monitor.py::execute_trade` emergency-close branch is inside `if status_b == OrderStatus.LEG_B_REJECTED` before fill polling.
- After `fill_b = await self._await_order_fill(order_id_b, timeout=30)`, `status_b` can become `OrderStatus.LEG_B_REJECTED` for rejected/canceled/expired snapshots.
- That later rejected status only influences `pair_status = PARTIAL_EXPOSURE`; there is no emergency close branch after fill polling.
- The function ends with `logger.info(f"TRADE EXECUTED: ... A=LEG_A_FILLED, B=LEG_B_FILLED")` even when `status_b` is rejected, partial, or submitted.

#### Trigger
Leg A fills, Leg B submit returns success/accepted, and the broker later reports Leg B rejected, canceled, expired, or otherwise terminal non-fill during order polling.

#### Broken assumption
Only an immediate Leg B submit error needs emergency-close handling.

#### Financial or workflow consequence
The bot can leave filled Leg A exposure open after Leg B fails at the broker, while logs imply the pair executed. That is unmanaged live exposure and can miss immediate liquidation.

#### Existing protection
Immediate Leg B submit error attempts emergency close, and unknown Leg B submit state blocks automation.

#### Missing protection
No emergency-close or manual-reconciliation branch for Leg B terminal non-fill discovered during fill polling; no accurate final log for partial/rejected pair states.

#### Smallest safe fix
After Leg B fill polling, if `status_b` is rejected/canceled/expired or partial/non-terminal, do not log normal execution. For terminal non-fill after Leg A full fill, attempt the same emergency-close path or mark `FAILED_REQUIRES_MANUAL_RECONCILIATION` if close cannot be safely confirmed.

#### Test required
Simulate Leg A full fill, Leg B submit success, and Leg B fill snapshot `{"status": "rejected"}`; assert emergency close is attempted or manual reconciliation is persisted, and no normal trade-executed success log/journal is emitted.

#### Validation command
`python -m pytest tests/unit/test_monitor.py::test_execute_trade_emergency_closes_leg_a_when_leg_b_fill_rejects_after_submit -q --asyncio-mode=auto`

#### Related issues
ISSUE-0001, ISSUE-0002, ISSUE-0021

#### Fix priority
P0

#### Notes
This is distinct from ISSUE-0001. ISSUE-0001 is about persisted visibility of partial exposure; this issue is about failing to repair a known one-sided exposure after delayed Leg B rejection.

Fixed 2026-05-08 in `src/monitor.py::execute_trade` by routing Leg B terminal non-fill snapshots found during fill polling through the same emergency-close/manual-reconciliation path used for immediate Leg B submit failures. Regression test added: `tests/unit/test_monitor.py::test_execute_trade_emergency_closes_leg_a_when_leg_b_fill_rejects_after_submit`. Validation passed: `python -m pytest tests/unit/test_monitor.py -q --asyncio-mode=auto`.

### ISSUE-0023 — FastMCP trade tool bypasses dashboard safety and logs an invalid ledger payload

Status: FIXED  
Severity: HIGH  
Area: orchestration  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-11  
Evidence type: code/test  
Confidence: HIGH  

#### Summary
`src/mcp_server.py` exposes an `execute_trade` tool on the FastMCP surface that sends a direct gRPC execution request rather than going through the monitor's paper/live, risk, quote, and reconciliation gates. It also calls `persistence_service.log_trade()` with `metadata` instead of the model field `metadata_json`, so the manual execution audit log can fail even when the gRPC call returns.

#### Evidence
- `src/mcp_server.py::execute_trade` accepts ticker, side, quantity, mode, and pair_id, creates one leg, and calls `execution_client.execute_trade(...)` directly.
- The tool does not check `settings.PAPER_TRADING`, quote freshness, risk sizing, pending exposure, broker reconciliation state, or dashboard auth/session.
- `src/mcp_server.py::execute_trade` logs `{"metadata": {...}}`, but `src/services/persistence_service.py::TradeLedger` maps the JSON column as Python attribute `metadata_json`.
- `infra/docker-compose.backend.yml` exposes `mcp-server` on port `8000`; `.brain/02_ARCHITECTURE_MAP.md` already flags FastMCP as a separate optional surface.
- `tests/unit/test_mcp_execute_trade_safety.py::test_mcp_execute_trade_rejects_or_uses_safe_ledger_payload` now proves the FastMCP tool rejects and does not call the gRPC execution client or ledger writer.

#### Trigger
An operator or external client calls the FastMCP `execute_trade` tool.

#### Broken assumption
The MCP manual execution tool is assumed to be a harmless control surface equivalent to the monitor/dashboard workflow.

#### Financial or workflow consequence
Today Java execution is dry-run guarded, but the tool can still bypass workflow safety, return misleading control-surface behavior, and fail to persist its audit record. If Java live brokerage is ever enabled, this becomes an uncontrolled order-submission path.

#### Existing protection
Java `Application` refuses to boot with `DRY_RUN=false`, and the Java broker router uses `MockBroker` in dry-run mode. FastMCP `execute_trade` now returns a rejected/disabled response before any gRPC execution or ledger write.

#### Missing protection
No safe routed FastMCP execution path through the monitor/dashboard risk, quote, paper/live, and reconciliation gates. FastMCP auth/exposure posture is still a separate deployment concern.

#### Smallest safe fix
Implemented: disable the FastMCP `execute_trade` tool by returning a rejected/disabled response before execution or persistence.

#### Test required
Call the FastMCP execution tool in a unit test with paper mode and assert no live execution path is used, required safety checks run or the tool rejects, and `log_trade` receives `metadata_json`.

#### Validation command
`python -m pytest tests/unit/test_mcp_execute_trade_safety.py::test_mcp_execute_trade_rejects_or_uses_safe_ledger_payload -q --asyncio-mode=auto`

#### Related issues
ISSUE-0005, ISSUE-0007, ISSUE-0016

#### Fix priority
P1

#### Notes
Fixed 2026-05-11 in `src/mcp_server.py` by rejecting FastMCP manual trade execution before it can call `execution_client.execute_trade()` or `persistence_service.log_trade()`. Regression test added: `tests/unit/test_mcp_execute_trade_safety.py::test_mcp_execute_trade_rejects_or_uses_safe_ledger_payload`. Validation passed: `python -m pytest -q tests/unit/test_mcp_execute_trade_safety.py::test_mcp_execute_trade_rejects_or_uses_safe_ledger_payload --asyncio-mode=auto`. Remaining risk: there is still no safe monitor-routed FastMCP execution path, and adjacent execution idempotency tests need a `mocker` fixture before they can run locally. Next recommended task is ISSUE-0006.

### ISSUE-0024 — Financial kill switch uses gross market value for hedged and short positions

Status: FIXED  
Severity: CRITICAL  
Area: exit  
Discovered in audit: 2026-05-08  
Last checked: 2026-05-08  
Evidence type: code  
Confidence: HIGH  

#### Summary
`_evaluate_exit_conditions()` calculates kill-switch loss from `current_value = qty_a * price_a + qty_b * price_b` versus `total_cost_basis`. That ignores whether each leg is long or short, so a short leg moving against the bot can increase `current_value` and avoid triggering the financial kill switch.

#### Evidence
- `src/monitor.py::_evaluate_exit_conditions` computes `current_value = (leg_a["quantity"] * p_a) + (leg_b["quantity"] * p_b)`.
- `src/services/risk_service.py::check_financial_kill_switch` interprets lower current value versus cost basis as loss.
- `get_open_signals()` preserves each leg's `side`, but the kill-switch calculation does not use side when valuing the position.
- Test search found kill-switch client/close-failure tests, but no directional pair PnL test for short/long financial stop-loss behavior.

#### Trigger
An open pair contains a short leg whose price rises enough to create realized/unrealized loss while gross combined market value stays flat or increases.

#### Broken assumption
Gross market value is assumed to represent pair loss for both long and short legs.

#### Financial or workflow consequence
The financial kill switch can miss losses on short exposure and fail to close a losing pair. That can directly miss an exit and allow unmanaged drawdown.

#### Existing protection
Statistical z-score stop-loss can still trigger independently, and zero/stale prices are skipped.

#### Missing protection
No directional unrealized PnL calculation for pair legs before calling the financial kill switch.

#### Smallest safe fix
Compute pair current PnL using each leg's side and entry price, then trigger the financial kill switch from directional loss relative to cost basis.

#### Test required
Build an open `Short-Long` signal where the short leg price rises enough to exceed `FINANCIAL_KILL_SWITCH_PCT`; assert `_close_position(..., ExitReason.KILL_SWITCH)` is called.

#### Validation command
`python -m pytest tests/unit/test_monitor.py::test_financial_kill_switch_uses_directional_pair_pnl -q --asyncio-mode=auto`

#### Related issues
ISSUE-0001, ISSUE-0010, ISSUE-0016

#### Fix priority
P0

#### Notes
This is a confirmed calculation-shape issue from code inspection. Exact live magnitude depends on pair composition and prices.

Fixed 2026-05-08 in `src/monitor.py::_evaluate_exit_conditions` by calculating directional pair PnL from stored leg side, entry price, current price, and quantity, then feeding `cost_basis + directional_pnl` into the existing financial kill-switch check. Regression test added: `tests/unit/test_monitor.py::test_financial_kill_switch_uses_directional_pair_pnl`. Validation passed: `python -m pytest -q tests/unit/test_monitor.py tests/unit/test_alpaca_provider.py tests/unit/test_spread_guard_unit.py tests/unit/test_startup_guards.py --asyncio-mode=auto`.

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
- Superseded 2026-05-08: the same focused execution-safety slice now passes with 49 passed after monitor unit fixtures were updated to match the current fill/reconciliation contract.

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

- Superseded 2026-05-08: the monitor unit suite is now green and isolated from real Postgres for this slice.

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
| Close partial fill quantity | A close snapshot with `status=filled` but `filled_qty` below the requested close quantity is not a full close. Ledger closure remains blocked. | `tests/unit/test_monitor.py::test_close_position_does_not_close_ledger_on_short_close_fill_quantity` | `python -m pytest tests/unit/test_monitor.py::test_close_position_success tests/unit/test_monitor.py::test_close_position_does_not_close_ledger_until_all_close_orders_fill tests/unit/test_monitor.py::test_close_position_does_not_close_ledger_on_short_close_fill_quantity -q --asyncio-mode=auto` |
| Startup recovery | `CLOSING` rows after restart are unresolved state, not automatically reopenable positions. Startup must pause for manual reconciliation. | `tests/unit/test_startup_guards.py::test_startup_blocks_when_unresolved_execution_state_exists` | `.venv/bin/python -m pytest tests/unit/test_startup_guards.py::test_startup_blocks_when_unresolved_execution_state_exists -q` |
| Close-failed startup recovery | `CLOSE_FAILED` is unresolved broker/ledger state after a close exception and must block startup. | `tests/unit/test_startup_guards.py::test_startup_treats_close_failed_as_unresolved_execution_state` | `python -m pytest tests/unit/test_startup_guards.py -q --asyncio-mode=auto` |
| Dashboard paper wallet | Paper mode must not place real broker wallet-sync orders. | `tests/unit/test_dashboard_wallet_sync.py` | `.venv/bin/python -m pytest tests/unit/test_dashboard_wallet_sync.py -q` |
| Spread guard | Missing, non-numeric, zero, or invalid bid/ask is not acceptable market data. Reject before risk and broker paths. | `tests/unit/test_spread_guard_unit.py::test_spread_guard_rejects_missing_bid_ask` | `.venv/bin/python -m pytest tests/unit/test_spread_guard_unit.py::test_spread_guard_rejects_missing_bid_ask -q` |
| Value-order budget accounting | Submitted or unknown value orders are not confirmed fills and must not mutate used budget; `/invest` must not duplicate budget updates. | `tests/unit/test_brokerage_service_budget.py` | `python -m pytest -q tests/unit/test_brokerage_service_budget.py tests/unit/test_brokerage_dispatcher.py tests/test_telegram_commands.py --asyncio-mode=auto` |
| Pending-order budget read | Failed pending-order value read is unknown exposure, not zero pending exposure. Block entry before risk/order. | `tests/unit/test_monitor.py::test_execute_trade_blocks_when_pending_orders_budget_read_fails` | `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_blocks_when_pending_orders_budget_read_fails -q` |
| Alpaca open-order read | Failed `list_orders(status='open')` is not an empty open-order book. | `tests/unit/test_alpaca_provider.py::test_alpaca_pending_orders_raise_on_fetch_failure` | `.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q` |
| Fill confirmation | Absence from open orders is not proof of fill when no order snapshot confirms terminal state. | `tests/unit/test_monitor.py::test_await_order_fill_does_not_assume_missing_open_order_is_filled` | `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_await_order_fill_does_not_assume_missing_open_order_is_filled -q` |
| Alpaca order snapshot read | Failed `get_order()` is not an empty order snapshot. | `tests/unit/test_alpaca_provider.py::test_alpaca_get_order_raises_on_fetch_failure` | `.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q` |
| Alpaca position read | Failed `get_position(ticker)` is not zero shares. Only real not-found position returns `[]`. | `tests/unit/test_alpaca_provider.py::test_alpaca_get_positions_for_ticker_raises_on_read_failure` | `.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q` |
| Alpaca portfolio read | Failed portfolio read is not an empty portfolio. | `tests/unit/test_alpaca_provider.py::test_alpaca_get_portfolio_raises_on_read_failure` | `.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q` |
| Alpaca account reads | Failed account cash/equity/buying-power reads are unknown account state, not `0.0`. Live execution blocks before risk/order. | `tests/unit/test_alpaca_provider.py::test_alpaca_account_reads_raise_on_api_failure`, `tests/unit/test_monitor.py::test_execute_trade_blocks_when_account_balance_read_fails` | `python -m pytest tests/unit/test_alpaca_provider.py::test_alpaca_account_reads_raise_on_api_failure tests/unit/test_monitor.py::test_execute_trade_blocks_when_account_balance_read_fails -q --asyncio-mode=auto` |
| Emergency close ambiguity | Emergency close `unknown` is not success. Persist orphan/manual reconciliation state. | `tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous` | `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous -q` |
| Emergency close fill confirmation | Emergency close submit success is not proof of flat exposure. The close order must be confirmed filled before logging success. | `tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_fill_unconfirmed`, `tests/unit/test_monitor.py::test_execute_trade_emergency_closes_leg_a_when_leg_b_fails` | `python -m pytest tests/unit/test_monitor.py::test_execute_trade_emergency_closes_leg_a_when_leg_b_fails tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_fill_unconfirmed -q --asyncio-mode=auto` |
| Backend Compose PostgreSQL secret | Missing `POSTGRES_PASSWORD` must fail deployment instead of booting Postgres with a committed fallback password. | `tests/unit/test_backend_compose_secrets.py::test_backend_compose_requires_postgres_password_without_default` | `python -m pytest tests/unit/test_backend_compose_secrets.py tests/unit/test_validate_deploy_env.py -q` |

Observed validation notes:

- `tests/unit/test_alpaca_provider.py -q` passed after provider read-failure patches.
- Focused monitor tests for successful entry and emergency close ambiguity passed, but are slow in the current environment.
- `tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_fill_unconfirmed` failed before the patch because only Leg A fill was polled and the emergency close submit logged success without a close fill snapshot.
- The three-test emergency-close slice passed after the patch: close success, close unknown, and close success with unconfirmed fill.
- Full `tests/unit/test_monitor.py -q --asyncio-mode=auto` still fails outside this patch: stale unit fixtures reach real Postgres, older crypto tests omit `max_allowed_fiat`, and `test_orchestrator_veto` now hits profit guard precedence. Do not treat the full monitor suite as green yet.
- `tests/unit/test_monitor.py::test_close_position_skips_sell_when_broker_has_no_shares` still attempted a real Postgres connection and failed on DNS/name resolution during one run; this is a test isolation problem to fix before claiming the monitor suite is green.
- 2026-05-08 P0-002 update: `tests/unit/test_monitor.py -q --asyncio-mode=auto` now passes with 17 passed after stale monitor fixtures were updated to provide fill snapshots, full risk metadata, and persistence mocks.
- 2026-05-08 P0-002 validation: `python -m pytest -q tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py --asyncio-mode=auto` passed with 49 passed.
- 2026-05-08 P0-001 validation: `python -m pytest -q tests/unit/test_backend_compose_secrets.py tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py tests/unit/test_validate_deploy_env.py --asyncio-mode=auto` passed with 53 passed.
- 2026-05-08 P0-004 validation: `python -m pytest -q tests/unit/test_backend_compose_secrets.py tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py tests/unit/test_validate_deploy_env.py --asyncio-mode=auto` passed with 54 passed after adding `CLOSE_FAILED` startup blocking.
- 2026-05-08 P1-007 validation: `python -m pytest -q tests/unit/test_backend_compose_secrets.py tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py tests/unit/test_validate_deploy_env.py --asyncio-mode=auto` passed with 58 passed after account read failures were made fail-closed.
- 2026-05-08 P1-002 close partial-fill validation: `python -m pytest tests/unit/test_monitor.py::test_close_position_success tests/unit/test_monitor.py::test_close_position_does_not_close_ledger_until_all_close_orders_fill tests/unit/test_monitor.py::test_close_position_does_not_close_ledger_on_short_close_fill_quantity -q --asyncio-mode=auto` passed with 3 passed; the focused execution-safety slice passed with 59 passed.
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
