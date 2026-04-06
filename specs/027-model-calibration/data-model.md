# Data Model: Model Calibration

This document defines the telemetry and audit schema updates for performance and fill analysis.

## New Entities

### LatencyMetric (Redis - Transient)
Tracks the high-frequency gRPC performance metrics.
- **Key**: `latency_metrics:{signal_id}`
- **Fields**:
  - `orchestrator_sent_ns`: Nanoseconds from `time.perf_counter_ns()`.
  - `engine_received_ns`: Nanoseconds from `System.nanoTime()`.
  - `engine_processed_ns`: Nanoseconds from `System.nanoTime()`.
  - `orchestrator_received_ns`: Nanoseconds from `time.perf_counter_ns()`.

### FillAnalysis (PostgreSQL - Audit)
Results of the Shadow Mode calibration audit.
- **Table**: `fill_analysis`
- **Fields**:
  - `trade_id`: FK to `trade_ledger`.
  - `theoretical_mid_price`: Price from the L2 snapshot top-of-book.
  - `vwap_fill_price`: Final price calculated by `MockBroker`.
  - `slippage_pct`: Percentage difference.
  - `achievability_status`: ENUM ('PERFECT', 'ACCEPTABLE', 'UNACHIEVABLE').
  - `audit_timestamp`: When the analysis was performed.

## Updated Entities

### TradeLedgerEntry (PostgreSQL)
- **New Field**: `latency_rtt_ns`: Total RTT for the execution request.
- **New Field**: `reasoning_metadata`: Now MUST include the full L2 snapshot levels used for the "Walk the Book" calculation.
