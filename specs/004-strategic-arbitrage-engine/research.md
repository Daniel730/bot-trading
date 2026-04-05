# Research: Strategic Arbitrage Engine

## Technical Decisions

### Multi-Window Z-Score Calculation
- **Decision**: Use `pandas.rolling` for calculating 30, 60, and 90-day moving averages and standard deviations of the price spread.
- **Rationale**: Multi-window analysis provides a "look-back" hierarchy that filters out high-frequency noise (30d) while acknowledging medium-term trends (90d). This reduces false positives in signal generation.
- **Alternatives Considered**: Exponentially Weighted Moving Average (EWMA) - rejected because simple rolling windows align better with standard pair trading literature.

### AI Validation (Quant-Fundamental Integration)
- **Decision**: Invoke Gemini CLI with a prompt focusing on "Structural Change vs technical noise" using recent news headlines and SEC filing metadata.
- **Rationale**: Large Language Models (LLMs) excel at identifying sentiment and specific fundamental triggers (e.g., mergers, lawsuits) that purely statistical models miss.
- **Alternatives Considered**: Using dedicated news sentiment APIs (e.g., StockNews) - rejected to leverage the reasoning capabilities of Gemini for complex "Structural Change" detection.

### Brokerage Integration (Trading 212)
- **Decision**: Use Basic Authentication with the official Beta API. Execute rebalancing via individual `Quantity` orders rather than the native "Pie" rebalance tool.
- **Rationale**: The native Pie rebalance tool is often opaque and doesn't allow for the granular atomic swaps required by mean-reversion strategies. Individual orders provide control over the "Sell-then-Buy" execution order to free up capital.
- **Alternatives Considered**: Native Pie API - rejected due to lack of quantity-based rebalancing support in many regions.

### Containerization & Communication
- **Decision**: Use Docker with SSE (Server-Sent Events) transport for FastMCP communication.
- **Rationale**: Standard `stdio` transport exits when the parent process finishes. SSE allows the `mcp-server` to remain persistent and accessible by the bot orchestrator across the Docker network.
- **Alternatives Considered**: Stdio transport - rejected due to lifecycle issues in background containers.

## Constraints & Best Practices
- **NYSE Hours**: Operating window 14:30 - 21:00 WET. Any signal outside this window must be ignored.
- **Rate Limiting**: Adhere to Trading 212's limit (approx. 5 req/min for free tier) using `tenacity` retries and jitter.
- **Atomicicity**: If the first leg of a swap (Sell) succeeds but the second (Buy) fails, the bot must alert via Telegram immediately.
