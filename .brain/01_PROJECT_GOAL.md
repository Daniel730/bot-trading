# Project Goal

## Mission

Alpha Arbitrage Bot is a statistical arbitrage research and execution framework for paired assets. It scans equity and crypto pairs, estimates spread relationships with Kalman filters, validates opportunities through risk and agent checks, and routes approved trades to paper execution or a live brokerage path when explicitly permitted.

The long-term goal is a safe, inspectable operator-grade bot:

- conservative signal generation;
- explainable risk gates;
- auditable order state;
- paper-first validation;
- dashboard visibility;
- no silent live-capital exposure.

## Current Product Shape

The repo contains three product surfaces:

- Python backend: monitor loop, data, signal logic, risk, brokerage facade, persistence, telemetry, dashboard API.
- React dashboard: operator console for login, telemetry, pairs, wallet sync, trades, settings, bot controls, and health.
- Java execution engine: gRPC sidecar with Redis idempotency, L2/VWAP/slippage checks, PostgreSQL audit persistence, and kill-switch surface.

The README describes Trading 212, Alpaca, Web3, paper shadow execution, and Java gRPC routing. Current code has narrowed the active Python brokerage facade to Alpaca; Trading 212 and Web3 live providers are now under `legacy/` or described historically. Treat this as an important documentation/code divergence.

## Current Safety Goal

The immediate goal is not performance. It is to prove that the bot cannot create unintended exposure through:

- duplicated orders;
- assumed fills;
- unknown broker submit state;
- partial fills;
- leg A filled while leg B fails;
- close orders that may or may not have executed;
- startup recovery that reopens unsafe state;
- stale budget or pending-order reads;
- missing bid/ask data;
- paper-mode UI actions accidentally placing live orders.

## Non-Goals Right Now

- Do not optimize pair count or latency before correctness.
- Do not broaden live venue support before Alpaca execution state is trustworthy.
- Do not make Java live brokerage executable yet.
- Do not tune strategy profitability while order-state safety is still under audit.
- Do not treat old audit green checks as current proof.

## Definition Of Done For The Current Audit Phase

The current audit phase is done only when:

- the focused execution-safety unit slice is green;
- ambiguous broker submits produce `NEEDS_MANUAL_RECONCILIATION`;
- partial fills and unknown fills do not lead to a second leg;
- close workflows require confirmed close fills before ledger closure;
- startup blocks when unresolved execution state exists;
- dashboard wallet actions in paper mode do not call the broker;
- soak/fault-injection evidence is refreshed after the active fixes;
- production checklist still says not approved until the longer gates pass.

## Human Operator Promise

The bot should always answer three questions for the operator:

1. What did it decide?
2. What state did it mutate?
3. What must a human reconcile before it continues?

If the answer is unclear, the bot should pause or require manual reconciliation rather than continue trading.
