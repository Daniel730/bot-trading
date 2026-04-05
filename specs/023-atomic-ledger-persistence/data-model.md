# Data Model: Atomic Ledger Persistence

## Redis Key Structure

### Idempotency Lock
- **Key**: `execution:inflight:{signal_id}`
- **Type**: Hash
- **Fields**:
  - `status`: String (PENDING, SUCCESS, FAILED, REJECTED)
  - `timestamp`: Long (milliseconds)
- **TTL**: 300 seconds (5 minutes) as a catastrophic fallback.

### Dead-Letter Queue (DLQ)
- **Key**: `dlq:execution:audit_ledger`
- **Type**: List
- **Values**: JSON string of `TradeAudit` object.

## PostgreSQL Schema (Existing)

### table: trade_ledger
- `signal_id`: UUID (Primary Key)
- `pair_id`: TEXT
- `ticker`: TEXT
- `side`: TEXT
- `requested_qty`: DECIMAL
- `requested_price`: DECIMAL
- `actual_vwap`: DECIMAL
- `status`: TEXT
- `latency_ms`: BIGINT
- `created_at`: TIMESTAMP (Default now())
