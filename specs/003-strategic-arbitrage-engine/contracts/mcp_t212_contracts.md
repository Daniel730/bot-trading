# Interface Contracts: Strategic Arbitrage Engine

## Brokerage API (Trading 212 Beta)

### Create Market Order
- **Endpoint**: `POST /api/v0/equity/orders/market`
- **Request Body**:
```json
{
  "ticker": "string",
  "quantity": number,
  "extendedHours": false
}
```
- **Auth**: `Basic <Base64(API_KEY:API_SECRET)>`

### Fetch Portfolio
- **Endpoint**: `GET /api/v0/equity/portfolio`
- **Response**: List of current holdings to sync `VirtualPieAsset.current_quantity`.

## MCP Tools (FastMCP)

### `analyze_news`
Used by Gemini CLI to validate signals based on sentiment.
- **Parameters**: 
  - `tickers`: `list[str]`
  - `headlines`: `list[str]`
- **Returns**: `{"sentiment": float, "structural_change": boolean, "rationale": string}`

### `assess_risk`
Used by Gemini CLI to calculate trade risk.
- **Parameters**: 
  - `pair`: `str` (e.g., "AAPL/MSFT")
  - `z_score`: `float`
- **Returns**: `{"risk_rating": string, "max_drawdown_est": float}`

### `telegram_confirm`
Triggered by Gemini CLI after validation to request user approval.
- **Parameters**: `message: str`
- **Action**: Sends async message with [APPROVE]/[REJECT] buttons.
