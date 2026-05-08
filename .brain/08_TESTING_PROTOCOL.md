# Testing Protocol

## Current Test Posture

The current focused execution-safety slice is not green.

Fresh result from 2026-05-07:

```bash
python -m pytest -q tests/unit/test_startup_guards.py tests/unit/test_alpaca_provider.py tests/unit/test_dashboard_wallet_sync.py tests/unit/test_monitor.py tests/unit/test_spread_guard_unit.py
```

Result:

- 42 passed.
- 6 failed.

Do not claim this branch is execution-safe until those failures are resolved.

## 2026-05-08 Targeted Safety Regression Evidence

The following focused tests were added or updated to protect one-issue safety fixes. Passing these commands proves only the named invariant, not full readiness.

Broker/provider state-read safety:

```bash
.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q
```

Protects:

- submit timeout reconciles by `client_order_id`;
- submit timeout that cannot reconcile returns `unknown`;
- failed pending-order read raises;
- failed order snapshot read raises;
- failed ticker position read raises except true not-found;
- failed portfolio read raises.

Entry and reconciliation safety:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_monitor.py::test_execute_trade_success_marks_both_final_legs_open_pair \
  tests/unit/test_monitor.py::test_execute_trade_blocks_when_pending_orders_budget_read_fails \
  tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_leg_a_submission_ambiguous \
  tests/unit/test_monitor.py::test_execute_trade_blocks_leg_b_without_confirmed_leg_a_fill \
  tests/unit/test_monitor.py::test_await_order_fill_does_not_assume_missing_open_order_is_filled \
  tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous \
  -q
```

Protects:

- fully opened pairs reload as two `OPEN_PAIR` legs;
- pending-order read failures block entries;
- unknown submits require manual reconciliation;
- Leg B waits for confirmed full Leg A fill;
- missing open order without snapshot is not assumed filled;
- ambiguous emergency close is orphan/manual-reconciliation state.

Close/startup/paper-mode safety:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_monitor.py::test_close_position_success \
  tests/unit/test_monitor.py::test_close_position_does_not_close_ledger_until_all_close_orders_fill \
  tests/unit/test_startup_guards.py::test_startup_blocks_when_unresolved_execution_state_exists \
  tests/unit/test_dashboard_wallet_sync.py \
  tests/unit/test_spread_guard_unit.py::test_spread_guard_rejects_missing_bid_ask \
  -q
```

Protects:

- live close ledger closure requires confirmed fill snapshots;
- unresolved startup execution state pauses scanning;
- paper-mode dashboard wallet sync avoids broker order placement;
- invalid bid/ask blocks before risk and broker calls.

Known testing caveat:

- `tests/unit/test_monitor.py::test_close_position_skips_sell_when_broker_has_no_shares` reached real Postgres during a targeted run. Fix test isolation before using the whole monitor unit file as a readiness gate.

## Minimum Local Gate Before Committing Execution Logic

Run:

```bash
python -m pytest -q tests/unit/test_monitor.py tests/unit/test_alpaca_provider.py tests/unit/test_spread_guard_unit.py tests/unit/test_startup_guards.py
```

Expected:

- all green;
- no unit test reaches real `postgres` host accidentally;
- no test waits through the full 30-second fill-poll timeout unless explicitly intended.

## Broader Python Gate

Run:

```bash
python -m pytest tests/ -v --asyncio-mode=auto
```

Use focused subsets first when changing:

```bash
python -m pytest -q tests/unit/test_pair_eligibility.py tests/unit/test_slippage_guard.py
python -m pytest -q tests/integration/test_brokerage_safety.py tests/integration/test_data_resilience.py
python -m pytest -q tests/integration/test_portfolio_orchestration.py
```

## Frontend Gate

Run from `frontend/`:

```bash
npm run lint
npm run test
npm run build
```

Focus areas for current audit:

- dashboard login/session response contract;
- SSE and WebSocket auth;
- paper-mode wallet sync UI expectations;
- degraded backend states.

## Java Gate

Run from `execution-engine/`:

```bash
gradle generateProto --no-daemon
gradle shadowJar --no-daemon
gradle test --no-daemon
```

Remember:

- no Gradle wrapper is currently documented;
- Java 21 is required;
- `DRY_RUN=true` is mandatory for runtime.

## Infra Gate

Run:

```bash
python scripts/validate_deploy_env.py .env
docker compose -f infra/docker-compose.yml ps
```

Before production sign-off, also run local build mode:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.local.yml up -d --build --remove-orphans
```

## Required Tests For Current Active Fixes

Add or keep tests for:

- missing/zero/non-numeric bid/ask rejects before risk and broker calls;
- pending-orders value read failure blocks execution and alerts;
- failed Alpaca pending-order, order snapshot, position, and portfolio reads raise instead of returning safe-looking empty state;
- Alpaca timeout reconciles by client order ID;
- Alpaca timeout that cannot reconcile returns `unknown` and does not fallback submit;
- monitor logs manual reconciliation and stops on leg A unknown submit;
- monitor blocks leg B unless leg A fill is fully confirmed;
- leg A partial fill marks `PARTIAL_EXPOSURE`;
- leg B unknown submit requires manual reconciliation;
- emergency close unknown/failure logs `FAILED_REQUIRES_MANUAL_RECONCILIATION`;
- emergency close success is not considered safe until fill is confirmed; this test is still open;
- close order unknown or unconfirmed fill keeps ledger unclosed;
- startup with unresolved execution state pauses;
- dashboard wallet sync in paper mode does not call broker.

## Test Smells To Fix Immediately

- A unit test reaches `postgres:5432`.
- A unit test assumes missing open order means filled.
- A unit test treats broker read failure as empty orders, empty positions, empty portfolio, empty order snapshot, or zero cash.
- A unit test passes a risk result without all fields used by monitor logging.
- A test asserts a high-level verdict without considering later guards, such as profit guard.
- A test does not mock `_await_order_fill()` when testing post-submit paths.

## Production Evidence Gate

Production approval requires:

- all relevant unit/integration tests green;
- deployment env validation green;
- Docker services healthy;
- clean logs after restart drills;
- 2-4 hour paper-mode soak minimum;
- active market scan cycle with non-zero pair processing;
- no unresolved ledger reconciliation rows;
- runbook updated.
