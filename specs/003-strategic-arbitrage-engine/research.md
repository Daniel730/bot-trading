# Research: Strategic Arbitrage Engine

## Decision: Data Sourcing (yfinance + Polygon.io)
- **Rationale**: yfinance provides a reliable, free source for historical daily data needed for the 30/60/90 day Z-Score windows. Polygon.io WebSockets offer low-latency real-time updates for active monitoring.
- **Alternatives considered**: 
  - Polygon.io only: Free tier has limited REST requests (5/min), making initial historical load slow. WebSockets are limited on the free tier, so strict rate limiting or intermittent polling is required.
  - Alpha Vantage: API limits are more restrictive for real-time usage.

## Decision: Statistical Engine (Z-Score & Cointegration)
- **Rationale**: Use `statsmodels` for initial cointegration (ADF test) and `pandas` for rolling mean/std calculations. Multi-window Z-Score (30, 60, 90) provides a "confidence" layer—if multiple windows align, the signal is stronger.
- **Implementation**: `rolling(window=N).mean()` and `rolling(window=N).std()`.

## Decision: AI Validation (FastMCP + Gemini)
- **Rationale**: Exposing `sentiment_analysis` and `risk_assessment` as MCP tools allows Gemini to ingest news data and return a structured "GO/NO-GO" decision. This keeps the validation logic external and leverage's Gemini's reasoning.
- **Tools**:
  - `analyze_news(tickers, headlines)`: Returns sentiment score and identifies structural events.
  - `assess_risk(pair, z_score, market_context)`: Returns risk rating.

## Decision: Broker Integration (Trading 212 Beta)
- **Rationale**: The Beta API supports market orders by quantity. Basic Auth (Base64) is standard for this endpoint.
- **Rate Limiting**: Implement a `Tenacity` retry decorator with exponential backoff to handle the 5 req/min limit on the free tier (if applicable) or brokerage-specific headers.

## Decision: Notifications (Async Telegram)
- **Rationale**: `python-telegram-bot` (async) allows non-blocking status updates. Sharpe Ratio and Drawdown will be calculated using `quantstats` or manual pandas logic on the local trade ledger.
- **Human-in-the-loop**: Use Telegram inline buttons for manual trade approval (Principle V).

## Decision: Deployment & Error Handling
- **Rationale**: Headless execution on a server (e.g., VPS). Custom exception `EquityNotOwned` to handle cases where a sell signal is triggered but the brokerage or local state is out of sync.
- **State**: SQLite for the "Virtual Pie" (Principle IV).
