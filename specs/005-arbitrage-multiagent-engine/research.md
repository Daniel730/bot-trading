# Research: Multi-Agent Arbitrage Engine

## Decision: Polygon.io WebSocket for Real-time Monitoring
- **Rationale**: Polygon.io provides high-fidelity, low-latency US market data. Using WebSockets ensures the bot detects Z-score deviations instantly within the 14:30-21:00 WET window. `yfinance` will be relegated to daily/hourly historical baseline calculation for cointegraion tests.
- **Alternatives Considered**: Alpha Vantage (higher latency), yfinance only (too slow for real-time arbitrage).

## Decision: LangGraph Adversarial Debate (Bull vs Bear)
- **Rationale**: Signals are sent to a LangGraph `Decision Core`. A "Bull Agent" and a "Bear Agent" execute in parallel to evaluate the same signal using different lenses (momentum/volume for Bull, resistance/macro-sentiment for Bear). An `Aggregator` node then uses the Gemini-powered News Analyst verdict to finalize the decision.
- **Alternatives Considered**: Sequential chain (biased by first agent), single-agent prompt (prone to hallucinations/confirmation bias).

## Decision: FastMCP for Tooling & Execution
- **Rationale**: Separates the Cognitive layer (LangGraph) from the Execution layer (FastMCP tools for brokerage, risk calculation). FastMCP provides a standardized interface for LLMs to safely query data and execute trades.
- **Alternatives Considered**: Direct function calling (harder to audit and scale).

## Decision: Monte Carlo VaR & Kelly Criterion
- **Rationale**: Statistical arbitrage requires precise risk management. Monte Carlo simulation handles the non-normal return distributions common in pair trading. Kelly Criterion (fractional 0.25x) provides the optimal sizing based on the "Confidence Score" output by the LangGraph debate.
- **Alternatives Considered**: Constant position sizing (inefficient), Historical VaR (misses fat-tail risks).

## Decision: QuantStats HTML Audit Reports
- **Rationale**: "Total Auditability" (Principle III) requires visual representation of performance. QuantStats generates professional tearsheets (Sharpe, Sortino, Drawdown) which will be automatically exported to the HTML auditor daily.
- **Alternatives Considered**: Custom matplotlib plots (too much overhead), CSV logs only (poor readability for audit).
