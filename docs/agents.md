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
