# Quickstart: Atomic Ledger Persistence

## Local Setup

1. **Redis Setup**: Ensure Redis is running (default: `localhost:6379`).
2. **PostgreSQL Setup**: Ensure the `trade_ledger` table exists in your database.
3. **Environment Configuration**:
   - `REDIS_URI`: `redis://localhost:6379`
   - `DB_URI`: `r2dbc:postgresql://user:pass@localhost:5432/db`

## Testing Idempotency

Send two identical gRPC requests using `grpcurl`:

```bash
grpcurl -plaintext -d '{"signal_id": "550e8400-e29b-41d4-a716-446655440000", "pair_id": "BTC-USD", "legs": [{"ticker": "BTC", "side": "SIDE_BUY", "quantity": 0.001, "target_price": 50000}], "max_slippage_pct": 0.01, "timestamp_ns": '$(date +%s%N)'}' localhost:50051 execution.ExecutionService/ExecuteTrade
```

The second request should return `Duplicate request - returning cached status`.

## Testing State Cleanup

Force a runtime error by sending a request with a malformed ticker (if validation is insufficient) and verify that Redis key `execution:inflight:<id>` still has its status updated to `FAILED` or `REJECTED`.

```bash
redis-cli HGETALL execution:inflight:<id>
```

## Testing Ledger Persistence

Simulate DB failure by temporarily stopping PostgreSQL and then sending a trade. Verify that:
1. The gRPC call returns a 500-range error.
2. The trade audit payload is stored in the Redis DLQ: `redis-cli LLEN trade:ledger:dlq`.
