# Critical Workflows

## 1. Startup Workflow

Path: `src/monitor.py`

1. Create `ArbitrageMonitor`.
2. Attach monitor to dashboard service.
3. Initialize active pair universe.
4. If `LIVE_CAPITAL_DANGER=true` and the resolved runtime is an actual live broker endpoint, verify Redis L2 entropy baselines.
5. Start dashboard/API runtime.
6. Send system-health notification.
7. Current active edit: call `_fail_fast_on_unresolved_execution_state()`.
8. If unresolved execution state exists, set `operational_status=PAUSED_REQUIRES_MANUAL_REVIEW`, notify, and stop scanning.
9. If clean, reset circuit breaker state to `NORMAL`.
10. Start scan loop and background scouting/rotation.

Audit rule: never reopen ambiguous `CLOSING` rows as `OPEN` during startup. A crash during close may mean a broker close order was submitted before the ledger update completed.

## 2. Pair Initialization Workflow

Path: `src/monitor.py`, `src/services/pair_eligibility_service.py`, `src/services/arbitrage_service.py`

1. Load configured pairs from `settings.ARBITRAGE_PAIRS` or crypto test pairs in dev mode.
2. Apply dashboard pair overrides from `data/pairs.json` when present.
3. Reject mixed crypto/equity, cross-session, cross-currency, expensive, or short-hold LSE pairs according to config.
4. Fetch historical prices.
5. Run cointegration and optional rolling stability checks.
6. Allocate/warm Kalman state.
7. Store active pairs in memory.

Audit rule: a pair rejected at eligibility should never allocate Kalman state or reach order logic.

## 3. Signal Workflow

Path: `src/monitor.py`

1. Scan loop fetches latest prices.
2. `process_pair()` gets or creates Kalman filter state.
3. Z-score is calculated from the prior state before absorbing the current tick.
4. Threshold gate checks `abs(z_score) > MONITOR_ENTRY_ZSCORE`.
5. Optional cost scaling may raise the entry threshold.
6. Orchestrator validates with macro, bull/bear, fundamentals, whale watcher, portfolio/risk confidence, and accuracy scaling.
7. Profit/friction guards can still veto after orchestrator.
8. Accepted signal moves toward approval and execution.

Audit rule: any veto should preserve the reason and avoid mutating trade state as if a trade was attempted.

## 4. Live Pair Entry Workflow

Path: `src/monitor.py::execute_trade`

Current intended fail-closed flow:

1. Fetch bid/ask for both legs.
2. Reject if bid/ask is missing, zero, nonnumeric, or spread exceeds `SPREAD_GUARD_MAX_PCT`.
3. Read account cash/equity/buying power.
4. Read pending-order value. Current active edit blocks execution if pending exposure cannot be read.
5. Apply budget service and risk service sizing.
6. Build pair legs from direction, prices, hedge ratio, and gross notional.
7. Submit leg A with deterministic `client_order_id={signal_id}-A`.
8. If submit state is `unknown` or `requires_reconciliation`, log `NEEDS_MANUAL_RECONCILIATION`, notify, and do not submit leg B.
9. Poll/order-snapshot leg A until filled.
10. If leg A is not confirmed fully filled, update status to rejection, partial exposure, or manual reconciliation and do not submit leg B.
11. Submit leg B with deterministic `client_order_id={signal_id}-B`.
12. If leg B is unknown, notify and require manual reconciliation.
13. If leg B is rejected after leg A fill, attempt emergency close of leg A.
14. If emergency close is unknown or failed, log `FAILED_REQUIRES_MANUAL_RECONCILIATION`.
15. Only when both legs have confirmed fills should final ledger rows be marked `OPEN_PAIR`.

Audit rule: never infer a fill from the absence of an open order.

## 5. Close Workflow

Path: `src/monitor.py::_evaluate_exit_conditions`

1. Read open signal/legs.
2. Evaluate kill switch, take profit, and stop loss.
3. Mark signal `CLOSING` before sending close orders.
4. Preflight sellable shares for broker sells.
5. Submit close orders with deterministic close client IDs.
6. If any close order submit is unknown, mark `NEEDS_MANUAL_RECONCILIATION` and stop.
7. If any close order fails after a prior confirmed close fill, mark `NEEDS_MANUAL_RECONCILIATION`.
8. Poll close fills and require confirmed fill quantities before ledger closure.
9. Re-read broker quantities for every closed leg and require zero residual exposure.
10. Only then calculate realized PnL and close the ledger.

Audit rule: ledger closure must reflect broker reality, not submitted intent.

## 6. Dashboard Wallet Sync Workflow

Path: `src/services/dashboard_service.py`

Current active edit:

- `_wallet_execution_mode()` returns `PAPER` when `settings.PAPER_TRADING` is true, otherwise the brokerage provider name.
- Wallet recommendations and coint wallet sync return synthetic paper orders in paper mode.
- In paper mode these dashboard actions must not call `brokerage_service.place_value_order()`.

Audit rule: UI convenience actions must respect the global paper/live boundary.

## 7. Alpaca Ambiguous Submit Workflow

Path: `src/services/brokerage/alpaca.py`

Current active edit:

1. Submit order with Alpaca.
2. If submit succeeds, return normalized success with `order_id` and `client_order_id`.
3. If submit raises timeout/connection/temporary-failure style exception and a `client_order_id` exists, query Alpaca by client order ID.
4. If reconciliation finds an order, treat it as success.
5. If reconciliation fails, return status `unknown` with `requires_reconciliation=true`.
6. Do not fall back to a second submit after an ambiguous submit.

Audit rule: network timeout after submit is not the same thing as order rejection.

## 8. Production Gate Workflow

Production approval requires all of this:

- focused execution safety tests green;
- full Python tests green or failures explicitly waived for non-runtime reasons;
- frontend lint/test/build green;
- Java `gradle test` green;
- deployment env validation green;
- 2-4 hour paper-mode soak;
- Redis/Postgres/execution-engine restart drills;
- clean post-recovery logs;
- active market scan cycle with non-zero pair processing;
- no unresolved ledger rows requiring reconciliation;
- operator runbook and rollback path verified.
