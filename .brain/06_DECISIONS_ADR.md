# Decisions ADR

## ADR-001: Production approval is withheld until safety gates pass

- Status: accepted.
- Context: readiness scans show good functional progress but unresolved test, soak, auth, and runtime-log concerns.
- Decision: do not declare production readiness yet.
- Consequence: paper mode and dry-run evidence remain the required path.

## ADR-002: Java execution engine must stay dry-run only

- Status: accepted.
- Context: `execution-engine` has gRPC execution/audit infrastructure but no production live Java broker wiring.
- Decision: keep `DRY_RUN=true` required and refuse `DRY_RUN=false`.
- Consequence: live brokerage remains in Python, currently through Alpaca facade.

## ADR-003: Unknown broker submit state is not failure and not success

- Status: active/current.
- Context: timeouts and connection resets can happen after broker acceptance.
- Decision: represent ambiguous submit as `status=unknown` plus `requires_reconciliation=true`.
- Consequence: monitor must not place follow-up legs or fallback resubmits until broker reality is reconciled.

## ADR-004: Leg B requires confirmed full leg A fill

- Status: active/current.
- Context: placing leg B after unconfirmed leg A can create wrong or unmatched exposure.
- Decision: poll/snapshot leg A and require full fill before leg B.
- Consequence: partial, rejected, canceled, expired, zero-fill, or unknown leg A blocks leg B and updates state accordingly.

## ADR-005: Startup recovery must fail closed on ambiguous close state

- Status: active/current.
- Context: previous behavior reopened `CLOSING` rows as `OPEN` after restart.
- Decision: convert unsafe `CLOSING` rows to manual reconciliation and pause startup if unresolved rows exist.
- Consequence: manual operator reconciliation is required before scans resume.

## ADR-006: Dashboard wallet actions respect paper mode

- Status: active/current.
- Context: wallet sync/recommendation buttons are operationally convenient but dangerous if they bypass mode.
- Decision: when `PAPER_TRADING=true`, return synthetic paper order records and do not call broker order placement.
- Consequence: dashboard messages should show `execution_mode=PAPER`.

## ADR-007: Alpaca is the current active brokerage facade

- Status: accepted by current code, docs need reconciliation.
- Context: `BrokerageService` logs that legacy providers moved to `legacy/` and initializes Alpaca regardless of requested provider.
- Decision in code: force Alpaca.
- Consequence: docs, `.env.template`, dashboard labels, and release checklist must not imply T212/Web3 live routing is currently active unless routing is restored with tests.

## ADR-008: Missing bid/ask fails closed

- Status: active/current.
- Context: a trade generated from last price but executed through unavailable or invalid bid/ask data can be economically false.
- Decision: missing, zero, invalid, or too-wide bid/ask rejects before risk checks and broker placement.
- Consequence: paper/live behavior should both preserve this invariant unless a test explicitly covers a paper-only exception.

## ADR-009: Local brain is now part of the repo workflow

- Status: accepted.
- Context: audits, fixes, and design intent were spread across README, docs, prompts, and historical notes.
- Decision: `.brain/` is the high-signal local memory.
- Consequence: update `.brain/` when changing architecture, safety posture, audit state, test gates, or release readiness.

## ADR-010: Unknown broker state must never become safe-looking state

- Status: active/current.
- Context: several Alpaca reads previously converted failures into `[]`, `{}`, or `0.0`.
- Decision: broker read failures that affect execution, reconciliation, exposure, or budget must be visible to callers. Empty orders/positions/portfolio are valid only when returned by a successful broker read.
- Consequence: `get_pending_orders()`, `get_order()`, `get_positions(ticker)`, and `get_portfolio()` raise on read failure. Account cash/equity/buying-power reads still need the same treatment.
- Protecting tests: `test_alpaca_pending_orders_raise_on_fetch_failure`, `test_alpaca_get_order_raises_on_fetch_failure`, `test_alpaca_get_positions_for_ticker_raises_on_read_failure`, `test_alpaca_get_portfolio_raises_on_read_failure`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_alpaca_provider.py -q`.

## ADR-011: Missing trades are safer than ambiguous exposure

- Status: active/current.
- Context: profitability pressure can tempt retry/fallback behavior when broker state is unclear.
- Decision: when execution state is ambiguous, fail closed, notify, and preserve manual reconciliation state. Do not optimize for capturing the trade.
- Consequence: pending-order read failure blocks entry; missing/invalid bid/ask blocks entry; unknown submit blocks follow-up legs; unconfirmed fill blocks ledger closure.
- Protecting tests: `test_execute_trade_blocks_when_pending_orders_budget_read_fails`, `test_spread_guard_rejects_missing_bid_ask`, `test_execute_trade_marks_manual_reconciliation_when_leg_a_submission_ambiguous`, `test_close_position_does_not_close_ledger_until_all_close_orders_fill`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_blocks_when_pending_orders_budget_read_fails tests/unit/test_spread_guard_unit.py::test_spread_guard_rejects_missing_bid_ask -q`.

## ADR-012: Emergency close ambiguity is orphan risk until proven otherwise

- Status: active/current.
- Context: after Leg A fills and Leg B fails, the emergency close is a capital-safety repair, not a normal order.
- Decision: emergency close `unknown` / `requires_reconciliation` is persisted as `FAILED_REQUIRES_MANUAL_RECONCILIATION`; it must not be logged as success.
- Consequence: operator reconciliation is required when emergency close state is unknown. A remaining open decision is to require fill confirmation before logging emergency close success.
- Protecting test: `tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous`.
- Validation command: `.venv/bin/python -m pytest tests/unit/test_monitor.py::test_execute_trade_marks_manual_reconciliation_when_emergency_close_ambiguous -q`.
