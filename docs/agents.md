# Agent Hierarchy

## Orchestrator (Multi-Agent Debate)
Coordinates adversarial signals from Bull, Bear, and Fundamental agents.
- **Responsibilities**: Parallel signal evaluation, SEC-based veto logic, consensus aggregation.
- **Resilience**: Implements `return_exceptions=True` in concurrent execution to ensure system uptime during individual agent or API failures.
- **Compliance**: Integrates region-aware hedging (DEFCON 1) with UCITS fallback support for EU regulated environments.

## PortfolioManagerAgent (Robo-Advisor)

## MacroEconomicAgent (Environment Monitor)
Provides global market context.
- **Responsibilities**: Monitoring interest rates (^TNX) and inflation data.
- **Logic**: RISK_ON / RISK_OFF state detection for allocation guidance.

## Execution Engine (Java Persistence & Idempotency)
Handles the low-latency execution and reliable persistence of trading signals.
- **Atomic Idempotency**: Uses Redis Lua scripts (pre-loaded with EVALSHA) to ensure "exactly-once" execution of every unique Signal ID, preventing duplicate trades during network retries.
- **Reliable Ledger Persistence**: Implements blocking writes to PostgreSQL (R2DBC) with a mandatory Redis-based Dead-Letter Queue (`dlq:execution:audit_ledger`) fallback to ensure a 100% audit trail even during database outages.
- **State Cleanup**: Employs a `try-finally` lifecycle to guarantee every order transitions to a terminal state (SUCCESS, REJECTED, or FAILED) in the distributed state store.
- **Concurrency**: Optimized for Java 21 Virtual Threads, ensuring non-blocking operations and high throughput under market volatility.
