# Interface Contracts: Trading Arbitrage Bot

**Feature**: 002-trading-arbitrage-bot
**Date**: 2026-03-27

## Brokerage API (Trading 212)

### Create Market Order
- **Endpoint**: `POST /api/v0/equity/orders/market`
- **Request Body**:
```json
{
  "ticker": "string",     // e.g. "AAPL_US_EQ"
  "quantity": number,     // positive for BUY, negative for SELL
  "extendedHours": false  // Enforced by Principle II
}
```
- **Response**: `201 Created` with order ID and initial status.

### Fetch Portfolio (Startup Sync)
- **Endpoint**: `GET /api/v0/equity/portfolio`
- **Response**: List of current positions (ticker, quantity) used to refresh `VirtualPieAsset.current_quantity`.

## MCP Tools (FastMCP)

### `get_market_prices`
Fetches current market state for monitoring.
- **Parameters**: `tickers: list[str]`
- **Returns**: OHLCV data.

### `get_news_context`
Retrieves recent headlines for AI validation.
- **Parameters**: `tickers: list[str]`
- **Returns**: Headlines from last 24h.

### `execute_arbitrage_trade`
Used by Gemini CLI to approve signals and trigger rebalancing.
- **Parameters**: `signal_id: str`, `ai_action: str` ("GO" or "NO-GO"), `rationale: str`
- **Action**: 
    - If "GO": Sends Telegram confirmation request to user.
    - If "NO-GO": Logs rationale and cancels the signal.

## Notification Interface (Telegram)

### Bot Alert & Confirmation
- **Format**: Markdown with Inline Buttons (Approve/Reject)
- **Required Fields**: Pair, Z-Score, AI Rationale.
