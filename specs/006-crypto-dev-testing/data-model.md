# Data Model: 24/7 Crypto Development Mode

## Configuration Extensions (`settings.py`)

| Field | Type | Description |
|-------|------|-------------|
| `DEV_MODE` | `bool` | Enables 24/7 monitoring and bypasses NYSE/NASDAQ hours. |
| `CRYPTO_TEST_PAIRS` | `List[Dict]` | List of crypto pairs (ticker_a, ticker_b) for `DEV_MODE`. |
| `DEV_EXECUTION_TICKERS` | `Dict` | Maps internal signal keys to T212-compatible stock tickers for technical validation. |

## Instrumented State (In-Memory)

The `AuditService` will maintain the following volatile state for SC-001 validation:

| Attribute | Type | Description |
|-----------|------|-------------|
| `total_cycles` | `int` | Count of monitoring loop iterations since startup. |
| `successful_cycles` | `int` | Count of iterations that successfully fetched data and completed analysis. |
| `last_connectivity_check` | `datetime` | Timestamp of the last successful T212/yfinance heartbeat. |

## Persistence (Existing Tables)

- **`signals`**: Signals generated in `DEV_MODE` will be persisted here with their Z-score and agent confidence.
- **`thought_journals`**: LLM/Agent reasoning for crypto pairs will be saved here for auditing.
- **`trade_records`**: If execution is triggered in `DEV_MODE`, records will be marked with `is_shadow=True` (unless explicitly testing live execution on small lots).

## State Transitions

1. **Initialization**: If `DEV_MODE=True`, `ArbitrageMonitor` loads `CRYPTO_TEST_PAIRS` instead of `ARBITRAGE_PAIRS`.
2. **Cycle**:
   - Check NYSE hours → Skip check if `DEV_MODE=True`.
   - Fetch Data → Use `yfinance` for crypto.
   - Analysis → Trigger Bulls/Bears/News Analyst (even if mock).
   - Validation → Log Connectivity Success Rate.
3. **Execution**: If signal approved, execute on `DEV_EXECUTION_TICKERS` via T212 API.
