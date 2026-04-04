# Contracts: Strategic Arbitrage Engine

## MCP Tools (Strategic Arbitrage Server)

### `analyze_news`
Called by the bot to validate signals via Gemini CLI.
- **Input**:
  - `tickers`: List[String]
  - `headlines`: List[String]
- **Output**: JSON object with `recommendation` ("GO"/"NO_GO") and `sentiment_score`.

### `record_ai_decision`
Called by Gemini CLI to persist its logic back to the bot.
- **Input**:
  - `signal_id`: String (UUID)
  - `status`: String ("GO"/"NO_GO")
  - `rationale`: String
- **Output**: Confirmation message.

## Brokerage Interface (Trading 212 Beta API)

### Market Order
- **Method**: POST
- **Endpoint**: `/api/v0/equity/orders/market`
- **Payload**:
  ```json
  {
    "ticker": "KO",
    "quantity": 1.5,
    "extendedHours": false
  }
  ```
- **Auth**: Basic (API Key : Secret)

### Portfolio Fetch
- **Method**: GET
- **Endpoint**: `/api/v0/equity/portfolio`
- **Output**: List of current holdings with `ticker` and `quantity`.

## Telegram Callbacks
- `approve_{signal_id}`: Triggers the execution loop for the pair.
- `reject_{signal_id}`: Marks the signal as rejected and suppresses execution.
