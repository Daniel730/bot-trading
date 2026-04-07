# Data Model: Model Calibration

This document defines telemetry and audit schema updates for performance and fill analysis.

## New Entities

### LatencyMetric (Redis - Transient)
Tracks the high-frequency gRPC performance metrics.
- **Key**: `latency_metrics:{signal_id}`
- **TTL**: 1 hour
- **Fields**:
  - `orchestrator_sent_ns`: `int64` (Python `time.perf_counter_ns()`)
  - `engine_received_ns`: `int64` (Java `System.nanoTime()`)
  - `engine_processed_ns`: `int64` (Java `System.nanoTime()`)
  - `orchestrator_received_ns`: `int64` (Python `time.perf_counter_ns()`)

### FillAnalysis (PostgreSQL - Audit)
Results of the Shadow Mode calibration audit.
- **Table**: `fill_analysis`
- **Fields**:
  - `trade_id`: FK to `trade_ledger`.
  - `theoretical_mid_price`: `numeric(18, 8)`
  - `vwap_fill_price`: `numeric(18, 8)`
  - `slippage_bps`: `int`
  - `achievability_status`: `ENUM('PERFECT', 'ACCEPTABLE', 'UNACHIEVABLE')`
  - `audit_timestamp`: `timestamptz`

## Updated Entities

### TradeLedgerEntry (PostgreSQL)
- **New Field**: `latency_rtt_ns`: `int64`
- **New Field**: `reasoning_metadata`: MUST include full L2 snapshot (top 10 levels).
- **New Field**: `clock_sync_status`: `bool` (from chrony check).

## Idempotency Lock (Redis)
- **Key**: `idempotency:{signal_id}`
- **Value**: `"LOCKED"`
- **TTL**: 60 seconds
- **Command**: `SET key "LOCKED" NX EX 60`
