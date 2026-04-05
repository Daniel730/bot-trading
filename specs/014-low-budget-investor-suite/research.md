# Research: Low-Budget Investor Suite

## Decision: Value-Based Order Simulation
- **Decision**: Manually calculate `quantity` in `BrokerageService` instead of relying on a native `VALUE` strategy.
- **Rationale**: Trading 212 Public API (v0) only supports `QUANTITY`. Attempting to use `VALUE` results in 400 errors or ignored fields.
- **Alternatives considered**: 
  - Using Internal API (v1): Rejected due to security risks (requires session cookies/tokens) and instability.
  - Rounding to 2 decimal places: Rejected in favor of 6 decimal places to better support micro-budgets (e.g., $1.00 buys of expensive stocks).

## Decision: DCA Scheduling via Asyncio Background Task
- **Decision**: Implement a `DCAService` that runs an internal `asyncio` loop, started by `ArbitrageMonitor`.
- **Rationale**: Avoids external dependencies like `apscheduler` while providing sufficient accuracy (1-minute resolution) for the required success criteria (60-minute window).
- **Alternatives considered**: 
  - Cron jobs: Rejected as it splits logic into system-level configs rather than keeping it in the Python codebase.

## Decision: Macro Data Sources
- **Decision**: Use `yfinance` for core indices and yields, supplemented by FRED (via `requests` if needed) for specific macro indicators like CPI/Inflation.
- **Rationale**: `yfinance` is already a core dependency. For "Investor Persona," tracking the 10Y Yield (`^TNX`) and S&P 500 (`^GSPC`) provides sufficient "Big Picture" context for risk-off/on decisions.
- **Tickers to monitor**:
  - `^TNX`: 10-Year Treasury Note Yield (Interest Rate proxy).
  - `^VIX`: CBOE Volatility Index (Risk proxy).
  - `SPY` / `QQQ`: Broader market trend.

## Decision: Multi-Agent Synthesis for "Thesis"
- **Decision**: The `PortfolioManagerAgent` will query the `audit_logs` table for the last N records related to a trade signal and use a specialized prompt to generate a natural language summary.
- **Rationale**: Reuse existing `Thought Journal` data (from Phase 010) to minimize LLM tokens and ensure consistency between internal logic and external explanation.
