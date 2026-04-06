# Tasks: Model Calibration

**Feature Branch**: `027-model-calibration`  
**Created**: 2026-04-06  
**Status**: Draft  
**Plan**: [specs/027-model-calibration/plan.md]

## Implementation Strategy

We will implement high-precision latency monitoring by adding gRPC interceptors to both the Python Orchestrator (Client) and Java Engine (Server). For fill achievability, we'll build a calibration service that compares simulated fills against captured L2 snapshots. Finally, we'll harden the Redis idempotency layer with Lua scripting and a dedicated stress test to ensure zero duplicate executions under high-frequency signal bursts.

## Phase 1: Setup

- [X] T001 Verify project structure for Python services in `src/services/`
- [X] T002 Verify project structure for Java interceptors in `execution-engine/src/main/java/com/arbitrage/engine/api/`

## Phase 2: Foundational (Monitoring & Infrastructure)

- [X] T003 [P] Implement `LatencyClientInterceptor` with nanosecond precision in `src/services/latency_interceptor.py`
- [X] T004 [P] Implement `LatencyServerInterceptor` with `System.nanoTime()` in `execution-engine/src/main/java/com/arbitrage/engine/api/LatencyInterceptor.java`
- [X] T005 Update gRPC client factory in Python to use the new interceptor in `src/mcp_server.py`
- [X] T006 Update gRPC server builder in Java to include the new interceptor in `execution-engine/src/main/java/com/arbitrage/engine/Application.java`

## Phase 3: [US1] Latency Performance Audit (Priority: P1)

**Story Goal**: Track and log gRPC RTT and decomposition metrics.

- [X] T007 [P] [US1] Create `LatencyMetric` record/model in Redis service in `src/services/redis_service.py`
- [X] T008 [US1] Implement `LatencyService` to push and aggregate performance metrics in `src/services/latency_service.py`
- [X] T009 [US1] Add integration test to verify sub-millisecond gRPC RTT in `tests/integration/test_latency_audit.py`

## Phase 4: [US2] Fill Achievability Analysis (Priority: P1)

**Story Goal**: Audit Shadow Mode fills against captured L2 snapshots.

- [X] T010 [P] [US2] Create `fill_analysis` table in PostgreSQL schema in `execution-engine/src/test/resources/init.sql` (and migration if needed)
- [X] T011 [US2] Implement `CalibrationService` to perform VWAP vs. Mid-Price analysis in `src/services/calibration_service.py`
- [X] T012 [US2] Add CLI command to trigger daily calibration reports in `scripts/calibration_analysis.py`

## Phase 5: [US3] Idempotency Stress Test (Priority: P2)

**Story Goal**: Ensure zero race conditions in Redis locking.

- [X] T013 [P] [US3] Implement atomic Lua script for idempotency check and status update in `execution-engine/src/main/java/com/arbitrage/engine/persistence/RedisOrderSync.java`
- [X] T014 [US3] Create `IdempotencyStressTest` using a high-concurrency load generator in `execution-engine/src/test/java/com/arbitrage/engine/stress/IdempotencyStressTest.java`
- [X] T015 [US3] Verify zero double-fire events under 100 req/s load in the stress test logs.

## Phase 6: Polish & Cross-cutting Concerns

- [ ] T016 Implement `LATENCY_ALARM` notification trigger in `src/services/notification_service.py`
- [ ] T017 Finalize `quickstart.md` with documented verification steps in `specs/027-model-calibration/quickstart.md`
- [ ] T018 Run the complete test suite to ensure no regressions in Shadow Mode or Live routing.

## Dependencies

1. US1 depends on Phase 2.
2. US2 depends on US1.
3. US3 is independent but recommended after US1.
4. Polish depends on all User Stories.

## Parallel Execution Examples

- **Example 1**: T003 (Python Interceptor) and T004 (Java Interceptor) are perfectly parallel.
- **Example 2**: T010 (SQL schema) and T011 (Python service) can start concurrently.
- **Example 3**: T013 (Lua script) and T014 (Stress test) are sequential but independent of the latency tasks.
