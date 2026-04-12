# Quickstart: Dynamic Risk and Volatility Switch

**Feature Branch**: `028-dynamic-risk-and-volatility-switch`  
**Created**: 2026-04-06

## Prerequisites

- Java Execution Engine running on port 50051.
- Redis (6379) and PostgreSQL (5432) active.
- `DEV_MODE=true` in `.env` for crypto baselining.

## 1. Baseline Entropy (DEV_MODE)

Monitor the real-time entropy of the crypto L2 book using the new volatility service:

```bash
# Start the volatility monitoring service
python3 -m src.services.volatility_service --baseline
```

Expect to see entropy values between 0.1 (Stable) and 0.9 (Volatile) for BTC-USD.

## 2. Simulate Drawdown (Risk Scaling)

To verify the `PerformanceMultiplier`, manually insert a losing trade into the ledger:

```sql
INSERT INTO trade_ledger (signal_id, ticker, side, requested_qty, requested_price, actual_vwap, status, created_at)
VALUES (gen_random_uuid(), 'BTC-USD', 'BUY', 1.0, 60000.0, 50000.0, 'SUCCESS', NOW() - INTERVAL '1 hour');
```

Then check the calculated risk scale in the logs:

```bash
tail -f logs/trading.log | grep "RiskScale"
```

The scale should decrease from 1.0 towards 0.0 as the drawdown is recognized.

## 3. Dynamic Slippage Verification (gRPC)

Trigger a trade during a period of high entropy (simulated or real) and check the gRPC interceptor logs:

```bash
# Check the sent max_slippage_pct in the client logs
grep "Sending ExecutionRequest" logs/grpc_client.log -A 5
```

The `max_slippage_pct` should be reduced (e.g., from 0.001 to 0.0005) if the `VolatilitySwitch` is `HIGH_VOLATILITY`.
