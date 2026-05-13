# Workflow Failure Map

Last updated: 2026-05-13

## Workflow: Market Data Ingestion

Steps:
1. Resolve provider configuration and symbol mapping.
2. Fetch quote/candle/fundamental inputs.
3. Normalize timestamps, sessions, and adjusted data.
4. Store/cache data for strategy and risk consumers.

Failure points:
- Calendar/session freshness now blocks full-day holidays, default US early closes, HKEX common half-days, LSE common half-days, Xetra Christmas/New Year closures, and common Euronext Amsterdam/Paris half-days. Operators should still watch for ad-hoc future exchange notices.
- Corporate-action event ingestion is not first-class, although adjusted-history changes now invalidate saved Kalman state.

Known issues:
- None currently listed.

Required tests:
- None currently listed.

## Workflow: Signal Generation

Steps:
1. Load pair state and strategy filters.
2. Calculate spread/z-score and strategy decision.
3. Apply fundamental, market, and freshness filters.
4. Emit entry/no-entry/exit candidate.

Failure points:
- Stale-but-present fundamental cache entries still lack a max-age check.

Known issues:
- None currently listed.

Required tests:
- Stale fundamental cache age guard test.

## Workflow: Risk Approval

Steps:
1. Load budget/cash/risk state.
2. Validate symbol, mode, provider, and data freshness.
3. Validate exposure, cash limits, and unknown-state guards.
4. Approve, block, or defer the trade.

Failure points:
- Stale-but-present fundamental cache entries still lack a max-age check.
- Dashboard wallet action can continue despite cash-limited state.
Known issues:
- None currently listed.

Required tests:
- Stale fundamental cache age guard test.

## Workflow: Order Submission

Steps:
1. Submit Leg A.
2. Poll/reconcile Leg A fill state.
3. Submit Leg B only if Leg A is safe to hedge.
4. Poll/reconcile Leg B fill state.
5. Persist final, partial, or manual-review state.

Failure points:
- None currently listed.

Known issues:
- None currently listed.

Required tests:
- None currently listed.

## Workflow: Broker Reconciliation

Steps:
1. Fetch open orders, fills, and positions.
2. Match broker state to persisted trade/order state.
3. Resolve terminal, partial, ambiguous, and orphan states.
4. Update dashboard and monitoring state.

Failure points:
- Persistence/gRPC faults still need live operator alert delivery outside the production evidence gate.
- Close metadata can overwrite forensic entry data.

Known issues:
- ISSUE-0019

Required tests:
- Full-close quantity verification test.
- Close metadata preservation test.

## Workflow: Position Monitoring

Steps:
1. Load open signals/trades/positions.
2. Fetch current market data.
3. Evaluate stop-loss, take-profit, kill switch, and stale-state exits.
4. Trigger exits or manual-review state.

Failure points:
- Background task failures may stop monitoring silently.

Known issues:
- ISSUE-0017

Required tests:
- Exit evaluation rejects invalid bid/ask.
- Background task exception is observed.

## Workflow: Exit Execution

Steps:
1. Select exit action from monitored position state.
2. Submit close orders or emergency liquidation.
3. Verify close fills and remaining broker positions.
4. Persist close state and audit metadata.

Failure points:
- Persistence faults can hide close failures.
- Close metadata can overwrite entry evidence.

Known issues:
- ISSUE-0009
- ISSUE-0017
- ISSUE-0019

Required tests:
- Persistence failure degrades operational state.
- Entry metadata survives close.

## Workflow: Emergency Stop

Steps:
1. Receive kill-switch/manual-stop signal.
2. Block new entries immediately.
3. Continue or prioritize exits/reconciliation.
4. Surface stopped/degraded state to operator.

Failure points:
- Background tasks lack central watchdog.

Known issues:
- ISSUE-0017

Required tests:
- Background task watchdog test.

## Workflow: Restart Recovery

Steps:
1. Start services and validate config/dependencies.
2. Load persisted trades, orders, positions, and risk state.
3. Reconcile broker state before entries.
4. Resume monitoring or block in manual review.

Failure points:
- Production readiness still depends on operator-provided recovery evidence.

Known issues:
- None currently listed.
Required tests:
- Ambiguous fill states block entries.

## Workflow: Dashboard Status

Steps:
1. Collect backend, broker, database, and bot-control state.
2. Render status, cash, open positions, and blocked workflows.
3. Accept operator commands only through safe paths.
4. Display degraded/manual-review conditions.

Failure points:
- None currently listed.

Known issues:
- None currently listed.

Required tests:
- Cash command formatter test now exists for ISSUE-0006.
