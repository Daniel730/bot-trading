# Prompt Library

The active prompt library lives in `docs/prompts/`. This file summarizes the order and preserves the local audit posture so future sessions can run the same kind of review.

## Master Audit Prompt

Use when starting a serious workflow-bug audit:

```text
Audit this arbitrage trading bot for confirmed workflow bugs, not style.
Find defects that can cause wrong trades, missed trades, duplicated orders,
stale decisions, false arbitrage signals, unhandled partial fills, broken
workflow state, incorrect PnL, incorrect risk exposure, strategy/backtest/live
mismatch, or silent failures.

For every finding, include exact location, concrete trigger sequence, expected
behavior, actual behavior, consequence, smallest safe fix, and a test.
Mark uncertainty as risk, not confirmed bug.
```

Source: `docs/prompts/bug_hunter_master.md`.

## Audit Order

Source: `docs/prompts/order.md`.

1. Map workflow.
2. Identify states and transitions.
3. Audit order execution.
4. Audit strategy correctness.
5. Audit data integrity.
6. Audit async/race conditions.
7. Audit error handling.
8. Define invariants.
9. Create tests.
10. Only then refactor.

## Focused Prompts

| Prompt | Use For |
|---|---|
| `1-map_workflow_before_judging.md` | Reconstruct startup, data, signal, validation, risk, order, fill, retry, shutdown flows before judging. |
| `2-state_machine_bugs.md` | Find invalid/missing/double/out-of-order state transitions and crash states. |
| `3-order_execution.md` | Audit duplicate orders, idempotency, partial fills, two-leg exposure, order side, symbol mapping, rounding, and restart reconciliation. |
| `4-strategy_correctness.md` | Audit false signals, live/backtest mismatch, lookahead, Kalman order, stale z-scores, fee/slippage math, timestamp mismatch. |
| `5-data_integrity.md` | Audit exceptions, retries, timeout ambiguity, rate limits, rollback/hedge paths, and critical invariants. |
| `6-race_condition.md` | Audit shared mutable state, concurrent scans, background tasks, balance races, duplicate handling. |
| `7-error_handling.md` | Similar to data integrity, focused on exception handling and workflow continuation. |
| `8-invariant_checks.md` | Audit symbol formats, precision, currency, timezone, API response validation, stale cache, broker/DB divergence. |
| `9-prove_workflow_cant_break.md` | Try to prove each major workflow is correct and identify missing branches. |
| `after_start_answer.md` | Clean the finding list: remove generic, speculative, or too-large items; rank by financial danger. |
| `start_bot.md` | Per-file workflow bug audit prompt. |

## Current Best Prompt For This Branch

Use this when continuing the active execution-safety work:

```text
Audit the current monitor and Alpaca execution path as a two-leg order state
machine. Focus only on confirmed workflow bugs around ambiguous submit,
fill polling, partial fills, leg B gating, emergency close, close confirmation,
startup recovery, and ledger status.

For each issue, show the exact function and state transition. Explain the
broker/ledger timeline that causes failure. Do not refactor. Give the smallest
safe fix and the unit test or fake-provider contract test that proves it.
```

## Prompt Hygiene

- Do not ask for style comments in these audits.
- Do not accept "could be" as a bug unless the trigger sequence is concrete.
- Do not propose large architecture rewrites before proving the broken branch.
- Do not mix production-readiness checklists with code-level bug findings.
- Always separate confirmed bug, serious risk, missing test, and old historical note.
