# Contracts: Strategic Arbitrage Engine

## MCP Tools (Strategic Arbitrage Server)

### `analyze_news`
Used by Gemini to evaluate if a signal is technical noise or structural change.
- **Input**:
  - `tickers`: List[String]
  - `headlines`: List[String]
- **Output**: JSON containing AI sentiment and "GO/NO-GO" recommendation.

### `record_ai_decision`
Called by Gemini to persist its validation logic and trigger user confirmation.
- **Input**:
  - `signal_id`: String (UUID)
  - `status`: String ("GO", "NO_GO")
  - `rationale`: String
- **Output**: Confirmation string.

### `assess_risk`
Calculates volatility-adjusted risk for a pair.
- **Input**:
  - `pair`: String (e.g., "KO/PEP")
  - `z_score`: Float
- **Output**: Risk rating (LOW, MEDIUM, HIGH) and max drawdown estimate.

## Brokerage Interface (Trading 212 Beta)

### `place_market_order`
- **Method**: POST
- **Endpoint**: `/api/v0/equity/orders/market`
- **Payload**:
  ```json
  {
    "ticker": "KO",
    "quantity": 1.25,
    "extendedHours": false
  }
  ```
- **Auth**: Basic Auth (API Key:Secret)

### `fetch_positions`
- **Method**: GET
- **Endpoint**: `/api/v0/equity/portfolio`
- **Output**: List of objects containing `ticker`, `quantity`, and `averagePrice`.

## Telegram Callbacks
- `approve_{signal_id}`: Triggers the execution of market orders for the pair.
- `reject_{signal_id}`: Cancels the signal and logs the user decision.
