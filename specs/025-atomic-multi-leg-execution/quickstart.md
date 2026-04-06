# Quickstart: Atomic Multi-Leg Execution

## Environment Setup

The execution engine requires PostgreSQL and Redis. For local development, use the provided Docker Compose file.

```bash
docker-compose -f docker-compose.backend.yml up -d postgres redis
```

## Running the Engine

Ensure you have Java 21 installed. Navigate to the `execution-engine` directory:

```bash
cd execution-engine
./gradlew run
```

The server will start on port `50051`.

## Testing Atomic Execution

### 1. Successful 2-Leg Trade

Submit a 2-leg request where both legs are within market depth and slippage limits.

```bash
grpcurl -plaintext -d '{
  "signal_id": "'$(uuidgen)'",
  "pair_id": "KO_PEP",
  "timestamp_ns": '$(date +%s%N)',
  "max_slippage_pct": 0.01,
  "legs": [
    {"ticker": "KO", "side": "SIDE_BUY", "quantity": 10.0, "target_price": 50.0},
    {"ticker": "PEP", "side": "SIDE_SELL", "quantity": 5.0, "target_price": 100.0}
  ]
}' localhost:50051 com.arbitrage.engine.ExecutionService/ExecuteTrade
```

**Expected**: `STATUS_SUCCESS` and `actual_vwap` for the first leg.

### 2. Atomic Failure (Slippage Veto)

Submit a request where one leg exceeds slippage.

```bash
grpcurl -plaintext -d '{
  "signal_id": "'$(uuidgen)'",
  "pair_id": "KO_PEP",
  "timestamp_ns": '$(date +%s%N)',
  "max_slippage_pct": 0.001,
  "legs": [
    {"ticker": "KO", "side": "SIDE_BUY", "quantity": 10.0, "target_price": 50.0},
    {"ticker": "PEP", "side": "SIDE_SELL", "quantity": 5.0, "target_price": 50.0}
  ]
}' localhost:50051 com.arbitrage.engine.ExecutionService/ExecuteTrade
```

**Expected**: `STATUS_REJECTED_SLIPPAGE`. Check the `trade_ledger` table to verify both legs were recorded as rejected.

## Verification Queries

Check the audit trail in PostgreSQL:

```sql
SELECT signal_id, ticker, side, actual_vwap, status, latency_ms 
FROM trade_ledger 
ORDER BY created_at DESC 
LIMIT 10;
```
