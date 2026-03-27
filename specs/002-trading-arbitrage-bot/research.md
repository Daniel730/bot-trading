# Research: Trading Arbitrage Bot Architecture

**Feature**: 002-trading-arbitrage-bot
**Date**: 2026-03-27

## Decision 1: Brokerage Integration (Trading 212)
- **Decision**: Use the official Public API (v0) for market orders and position syncing.
- **Rationale**: While unofficial wrappers exist, the official API provides a stable, documented interface for Invest/ISA accounts.
- **Implementation**: 
    - `POST /api/v0/equity/orders/market` for execution.
    - `GET /api/v0/equity/portfolio` for startup quantity re-syncing (Clarification Session 2026-03-27).
    - Basic Auth using `API_KEY:API_SECRET`.
    - Implement a 2-second rate limit between orders as a safety margin.

## Decision 2: AI Agent Orchestration (FastMCP)
- **Decision**: Use FastMCP to expose Python tools to Gemini CLI.
- **Rationale**: FastMCP simplifies the creation of Model Context Protocol servers, allowing Gemini to "call" tools for fetching prices, validating news, and executing trades.
- **Tools to expose**:
    - `get_market_prices(tickers: list[str])`: Returns latest OHLCV.
    - `get_news_context(tickers: list[str])`: Returns recent headlines for validation.
    - `execute_arbitrage_trade(signal_id: str, action: str)`: Sends the order to T212 if approved.
    - `get_virtual_pie_status()`: Reads SQLite state.

## Decision 3: Market Data Sourcing (Polygon.io & yfinance)
- **Decision**: Use Polygon.io "All Tickers" Snapshot API for near real-time monitoring and `yfinance` for historical cointegration calculations.
- **Rationale**: Polygon's free WebSocket is limited to 1 ticker. The Snapshot API allows fetching the entire market state 5 times per minute, which is sufficient for 12-second update intervals. `yfinance` is the industry standard for reliable historical daily data.
- **Update Frequency**: 12-15 seconds (aligned with Polygon Free Tier limits).
- **Lookback Window**: 30-90 days for Z-score calculation.

## Decision 4: Local State & "Virtual Pie"
- **Decision**: SQLite for persistence with Startup API Re-sync.
- **Rationale**: Lightweight, serverless, and robust for tracking target weights. Startup re-sync ensures the current state matches the brokerage regardless of local DB drift.
- **Schema**:
    - `virtual_pie`: `ticker` (PK), `target_weight`, `current_quantity`, `last_price`.
    - `audit_log`: `timestamp`, `tickers`, `z_score`, `ai_recommendation`, `action_taken`, `brokerage_order_id`.

## Decision 5: Scheduling and Operating Hours
- **Decision**: Use `pytz` for timezone management and a simple loop with `time.sleep`.
- **Rationale**: Operating only during NYSE Regular Trading Hours (14:30 - 21:00 WET) is a core constitutional principle. The bot must check `pytz.timezone('America/New_York')` and NYSE holiday schedules.
