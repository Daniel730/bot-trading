# Tasks: Model Calibration

**Feature**: `027-model-calibration` | **Status**: Active | **MVP**: User Story 1

## Implementation Strategy

We will follow an incremental delivery approach, starting with high-precision latency measurement (US1), followed by fill realism analysis (US2), and concluding with idempotency hardening (US3). 

1. **Setup**: Initialize metrics storage and logging.
2. **Foundational**: Implement the gRPC interceptor framework in both Python and Java.
3. **User Stories**: Implement the specific logic for each story in priority order.
4. **Polish**: Add alarms, observability, and final performance tuning.

---

## Phase 1: Setup

- [X] T001 Initialize Redis keyspace for `latency_metrics:*` per `data-model.md`
- [X] T002 Create PostgreSQL migration for `fill_analysis` table and `trade_ledger` updates in `src/db/migrations/`
- [X] T003 [P] Add `latency_rtt_ns` and `reasoning_metadata` fields to `TradeLedgerEntry` model in `src/models/trade.py`

## Phase 2: Foundational

- [X] T004 [P] Implement `LatencyClientInterceptor` using `time.perf_counter_ns()` in `src/services/execution_service_client.py`
- [X] T005 [P] Implement Java `LatencyInterceptor` using `System.nanoTime()` in `execution-engine/src/main/java/com/bot/execution/interceptor/LatencyInterceptor.java`
- [X] T006 [P] Define `x-sent-ns`, `x-received-ns`, and `x-processed-ns` gRPC metadata headers in common protobuf definitions

---

## Phase 3: User Story 1 - Latency Performance Audit (P1)

**Story Goal**: Monitor end-to-end gRPC communication delay between Python and Java.
**Independent Test**: Run a Shadow Mode execution loop and verify `latency_metrics` are recorded in Redis and `TradeLedgerEntry`.

- [X] T007 [US1] Implement "Alpha Stale Time" calculation in `src/services/performance_service.py`
- [X] T008 [US1] Record `latency_rtt_ns` to `TradeLedgerEntry` upon successful execution in `src/services/execution_service_client.py`
- [X] T009 [US1] Implement `LATENCY_ALARM` trigger if gRPC RTT consistently exceeds 1ms in `src/monitor.py`
- [X] T010 [P] [US1] Create unit tests for high-precision latency calculations in `tests/unit/test_latency.py`

---

## Phase 4: User Story 2 - Fill Achievability Analysis (P1)

**Story Goal**: Audit Shadow Mode fill prices against L2 liquidity reality.
**Independent Test**: Verify that `reasoning_metadata` for every trade contains the L2 snapshot and VWAP matches the "Walk the Book" logic.

- [X] T011 [US2] Update `MockBroker` to include full L2 snapshot levels in `reasoning_metadata` in `src/services/brokerage_service.py`
- [X] T012 [US2] Implement `CalibrationService` for auditing `actual_vwap` vs. `L2 snapshot` in `src/services/calibration_service.py`
- [X] T013 [US2] Create logic to identify "unachievable" targets (spread < simulated slippage) in `src/services/calibration_service.py`
- [X] T014 [US2] Implement `FillAnalysis` record generation in `src/services/calibration_service.py`
- [X] T015 [P] [US2] Create integration tests for VWAP validation against L2 snapshots in `tests/integration/test_calibration.py`

---

## Phase 5: User Story 3 - Idempotency Stress Test (P2)

**Story Goal**: Verify Redis-based idempotency locks are robust under heavy load.
**Independent Test**: Send 100 duplicate `signal_id` requests per second and verify zero duplicate executions.

- [X] T016 [US3] Implement Redis `SET NX EX` idempotency lock in `src/services/execution_service_client.py`
- [X] T017 [US3] Implement Lua script for atomic status-based checks (e.g., retry logic) in `src/services/execution_service_client.py`
- [X] T018 [US3] Handle "Duplicate Request" status and prevent broker/simulation triggers in `src/services/execution_service_client.py`
- [X] T019 [P] [US3] Create load test for idempotency locks in `tests/benchmark/test_idempotency_load.py`

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T020 Optimize Redis metrics storage with a TTL to prevent memory bloat
- [X] T021 [P] Ensure clock synchronization (NTP/Chrony) verification in `scripts/verify_sc.py`
- [X] T022 Final audit of logging format for "Model Calibration" performance reports
- [X] T023 [P] Update `GEMINI.md` and `docs/agents.md` with new calibration telemetry details

## Dependencies

- Phase 2 (Foundational) MUST be completed before Phase 3 (US1).
- Phase 1 (Setup) migrations MUST be applied before any story-specific data persistence.

## Parallel Execution Examples

- **Story 1 & 2**: T004 (Python Interceptor) and T005 (Java Interceptor) can run in parallel.
- **Story 2**: T011 (MockBroker updates) and T012 (CalibrationService) can run in parallel.
- **Story 3**: T019 (Load test) can be developed in parallel with T016-T018 logic.
