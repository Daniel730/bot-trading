# Research: Model Calibration

This research documents decisions and rationale for performance monitoring and idempotency stress testing.

## Decision 1: High-Precision gRPC Latency Measurement

**Goal**: Monitor sub-millisecond gRPC RTT between Python and Java.

**Findings**:
- **Python-side**: Using `time.perf_counter_ns()` provides nanosecond precision for measuring the request start and end. A custom gRPC client interceptor can capture these timestamps without cluttering the business logic.
- **Java-side**: Using `System.nanoTime()` in a `ServerInterceptor` allows measuring the time from the moment the request hits the server to the point it is processed.
- **Clock Sync Issue**: Measuring "received - sent" directly requires perfectly synced clocks (PTP/NTP). To avoid this, we will primarily track **gRPC RTT** (Client Sent → Server Received → Processed → Client Received) and decompose it into **Transport Time** and **Engine Time**.

**Final Decision**: Implement a custom `LatencyInterceptor` in both Java (server-side) and Python (client-side) using high-precision nanosecond timers.

---

## Decision 2: Redis Idempotency Strategy under Stress

**Goal**: Prevent duplicate execution signals with zero race conditions under load.

**Findings**:
- **Atomic SET NX**: `SET signal_id "LOCKED" NX EX 30` is atomic and highly performant. If it returns `null`, the signal is already being processed.
- **Lua Scripting**: Allows complex checks (e.g., status verification) within a single atomic operation. However, for a simple lock, `SET NX` is faster and reduces Redis CPU load.
- **Double-fire Scenario**: If two requests hit Redis at the same microsecond, only the one that successfully performs `SET NX` will proceed.

**Final Decision**: Use Redis `SET key value NX EX <seconds>` for the primary idempotency lock. For status-based checks (e.g., re-running a failed signal), use a Lua script to ensure the state transition is atomic.

---

## Decision 3: Shadow Mode Fill Achievability Audit

**Goal**: Verify that theoretical fills match L2 reality.

**Findings**:
- **VWAP Calculation**: The "Walk the Book" logic implemented in feature 026 is mathematically correct. The validation step must now compare this VWAP with the **theoretical spread** (Mid-Price ± 0.1%).
- **Achievability Metric**: A fill is "unachievable" if the `actual_vwap` is worse than the target price + 50% of the calculated spread.

**Final Decision**: Create a `CalibrationService` in Python that pulls PAPER trade records from the PostgreSQL database and compares `actual_vwap` with the `L2 snapshot` captured in the `reasoning_metadata`.
