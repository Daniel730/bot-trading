# Data Model: Atomic Multi-Leg Execution

## Persistent Entities

### `trade_ledger` (PostgreSQL)

This entity tracks the audit trail of every execution attempt. For a multi-leg trade, multiple rows share the same `signal_id`.

| Field             | Type            | Description                                      |
|-------------------|-----------------|--------------------------------------------------|
| `id`              | SERIAL (PK)     | Auto-incrementing identifier                     |
| `signal_id`       | UUID            | Correlation ID linking multiple legs together    |
| `pair_id`         | VARCHAR(20)     | Name of the arbitrage pair (e.g., "KO_PEP")      |
| `ticker`          | VARCHAR(10)     | Asset symbol for this leg                        |
| `side`            | VARCHAR(10)     | "BUY" or "SELL"                                  |
| `requested_qty`   | DECIMAL(18,10)  | Quantity requested by the alpha agent           |
| `requested_price` | DECIMAL(18,10)  | Target price from the strategy signal           |
| `actual_vwap`     | DECIMAL(18,10)  | VWAP calculated from L2 order book (0 if failed) |
| `status`          | VARCHAR(50)     | Status: "SUCCESS", "REJECTED_SLIPPAGE", etc.     |
| `latency_ms`      | BIGINT          | Time from request receipt to persistence completion|
| `created_at`      | TIMESTAMP       | Record creation time                             |

## In-Memory Models (Java)

### `TradeAudit` (Record)

A lightweight container used to pass audit details between the `ExecutionServiceImpl` and `TradeLedgerRepository`.

```java
public record TradeAudit(
    String ticker,
    String side,
    BigDecimal requestedQty,
    BigDecimal requestedPrice,
    BigDecimal actualVwap
) {}
```

## Validation Rules

1.  **Signal ID**: Must be a valid UUID.
2.  **Ticker**: Must exist in the list of tickers provided by the L2FeedService.
3.  **Slippage**: `abs(actual_vwap - target_price) / target_price` must be <= `max_slippage_pct`.
4.  **Market Depth**: The total quantity of levels in the order book must be >= `requested_qty`.
5.  **Atomicity**: Either ALL rows for a `signal_id` are saved, or none are (achieved via R2DBC connection/statement lifecycle).
