# Feature Specification: Model Calibration

**Feature Branch**: `027-model-calibration`  
**Created**: 2026-04-06  
**Status**: Draft  

## User Scenarios & Testing

### User Story 1 - Latency Performance Audit (Priority: P1)

As a quant engineer, I want to monitor the end-to-end gRPC communication delay between the Python Orchestrator and the Java Execution Engine, so I can ensure our arbitrage signals are not becoming stale.

**Independent Test**: Run a continuous execution loop in Shadow Mode and log RTT. Verify RTT is recorded in `TradeLedgerEntry`.

**Acceptance Scenarios**:
1. **Given** a high-frequency signal burst, **When** the Python Orchestrator sends a trade request, **Then** the Java Engine must receive it within 500μs (measured via `x-received-ns` - `x-sent-ns`).
2. **Given** continuous operation, **When** the gRPC RTT exceeds 2ms for **5 consecutive samples**, **Then** the system must generate a `LATENCY_ALARM`.

---

### User Story 2 - Fill Achievability Analysis (Priority: P1)

As a quantitative analyst, I want to audit simulated fill prices against L2 liquidity reality.

**Independent Test**: Verify `reasoning_metadata` contains L2 snapshots (top 10 levels) and VWAP calculation matches the "Walk the Book" model.

**Acceptance Scenarios**:
1. **Given** a Shadow Trade, **When** quantity exceeds the top level of the L2 book, **Then** the recorded price must reflect a "Walk-the-Book" VWAP using a minimum of 5 levels of depth.

---

### User Story 3 - Idempotency Stress Test (Priority: P2)

As a system operator, I want to verify Redis-based idempotency locks are robust under heavy load.

**Independent Test**: Send 100 duplicate `signal_id` requests per second; verify zero duplicate executions in `TradeLedgerRepository`.

**Acceptance Scenarios**:
1. **Given** simultaneous identical signal requests, **When** the first is processing, **Then** subsequent requests must receive a `409 Conflict` (Duplicate Request) status.

## Requirements

### Functional Requirements

- **FR-001**: System MUST implement high-precision latency interceptors in both gRPC client (Python: `time.perf_counter_ns()`) and server (Java: `System.nanoTime()`).
- **FR-002**: System MUST calculate "Alpha Stale Time" (Engine Received - Orchestrator Sent) in **nanoseconds**.
- **FR-003**: System MUST provide a daily CSV report of Shadow Mode fill accuracy: `[trade_id, theoretical_mid, actual_vwap, slippage_bps, status]`.
- **FR-004**: L2 snapshot validity: Verify snapshot is < 100ms old at execution time.
- **FR-005**: Redis idempotency: Use `SET idempotency:{signal_id} "LOCKED" NX EX 60`.
- **FR-006**: `LATENCY_ALARM`: Trigger if RTT > 1ms for > 10% of samples over a 1-minute window.
- **FR-007 (Clock Sync)**: All environments MUST run `chrony` with a shared PTP/NTP source. Metrics are INVALID if clock drift > 100μs.
- **FR-008 (Idempotency)**: If Redis is unavailable, system MUST fail-safe and REJECT all execution requests.
- **FR-009 (Liquidity)**: Simulated fills MUST apply a 0.5bps "Market Impact" penalty for every 10% of top-level depth consumed.

## Success Criteria

- **SC-001**: Average gRPC latency < 0.8ms.
- **SC-002**: Shadow Mode fill prices 100% verifiable against captured L2 snapshots (top 10 levels).
- **SC-003**: Zero (0) duplicate execution records under load (1000 req/sec duplicate test).
- **SC-004**: System identifies 100% of "unachievable" targets where spread < (slippage + impact).

## Assumptions
- **Clock Synchronization**: Enforced via `chrony` (FR-007).
- **L2 Snapshots**: Captured via Feature 026.
- **Redis Availability**: Critical dependency (FR-008).
