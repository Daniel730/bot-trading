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

## ReflectionAgent (Learning Loop)
Handles post-trade evaluation and self-correction.
- **Responsibilities**: Vectorized trade post-mortems, agent weight updates.
- **Logic**: 30-day performance review, dynamic confidence adjustment.

## Decoupled Fundamental RAG (Asynchronous SEC Analysis)
Separates high-latency financial statement analysis from the real-time signal evaluation path.
- **Process Isolation**: A standalone background daemon (`src/daemons/sec_fundamental_worker.py`) executes in a dedicated Docker container to prevent GIL stalls in the main trading loop.
- **Materialized View**: Fundamental integrity scores are cached in Redis with a 24-hour TTL, enabling sub-millisecond retrieval during signal debates.
- **Deterministic Universe**: The background worker automatically analyzes all tickers defined in the `active_pairs` database, ensuring cache readiness before signals fire.
- **Resilience**: The worker implements exponential backoff for SEC EDGAR API rate limits, while the Orchestrator provides a safe default (50) and high-priority telemetry alerts on cache misses.
