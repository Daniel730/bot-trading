# Research: Strategic Arbitrage Engine

## Technical Decisions

### Cointegration and Z-Score Calculation
- **Decision**: Use `statsmodels` for OLS (Ordinary Least Squares) to determine hedge ratios and `pandas` for rolling Z-Score calculations.
- **Rationale**: `statsmodels` provides robust statistical tools for time-series analysis. Multi-window Z-Scores (30, 60, 90 days) are necessary to filter out short-term noise while capturing medium-term trends.
- **Alternatives Considered**: `scipy.stats` (rejected for less comprehensive time-series support).

### Fundamental AI Validation
- **Decision**: Integrate Gemini CLI with `FastMCP` to analyze SEC filings and earnings news.
- **Rationale**: Gemini CLI allows for complex reasoning over financial documents. Using `FastMCP` enables the AI to use custom tools like `analyze_news` and `assess_risk`.
- **Alternatives Considered**: OpenAI API (rejected to leverage existing Gemini CLI infrastructure).

### Brokerage Integration (Trading 212)
- **Decision**: Use the official Trading 212 Beta API with individual market orders by quantity.
- **Rationale**: Native "Pie" APIs are often restricted. Individual orders provide full control over rebalancing and allow for "Virtual Pie" management.
- **Alternatives Considered**: Selenium-based automation (rejected for fragility and security risks).

### Containerization and Orchestration
- **Decision**: Use Docker with a two-service setup (Bot + MCP Server) and SSE transport for communication.
- **Rationale**: SSE (Server-Sent Events) transport is persistent and suitable for network-based communication between containers in a non-interactive environment.
- **Alternatives Considered**: `stdio` transport (rejected as it exits immediately in background Docker processes).

## Constraints & Best Practices
- **NYSE Operating Hours**: Must strictly adhere to 14:30 - 21:00 WET.
- **Rate Limiting**: Polygon.io Free Tier limits to 5 requests per minute.
- **Human-in-the-Loop**: All trades require Telegram approval to act as a manual circuit breaker.
- **Atomicidade**: "Sell-then-Buy" sequence to ensure capital availability and minimize exposure.
