# Tasks: High-Performance Execution Engine (The Muscle)

**Input**: Design documents from `/specs/022-java-execution-engine/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/execution.proto

## Phase 0: Setup (P0: Gradle Scaffold & Protobuf Config)

**Purpose**: Project initialization and gRPC infrastructure.

- [x] T001 Create `execution-engine` directory structure at repository root.
- [x] T002 Initialize Gradle project with Kotlin DSL (`build.gradle.kts`).
- [x] T003 [P] Configure `protobuf-gradle-plugin` to generate Java code from `src/main/proto/execution.proto`.
- [x] T004 [P] Add dependencies: `grpc-netty-shaded`, `r2dbc-postgresql`, `lettuce-core`, `micrometer`, `jackson-databind`.
- [x] T005 [P] Add test dependencies: `junit-jupiter`, `testcontainers-postgresql`, `mockito`.
- [x] T006 Configure Java 21 toolchain and enable Virtual Threads for the application.
- [x] T007 [P] Create `Dockerfile` for distroless Java 21 deployment.

---

## Phase 1: Foundational (P1: VWAP 'Walk the Book' Logic & BigDecimal Math)

**Purpose**: Core mathematical engine and precision-first domain models.

- [x] T008 [P] Implement `ExecutionLeg` domain model using `java.math.BigDecimal` for price and quantity in `src/main/java/com/arbitrage/engine/core/models/`.
- [x] T009 [P] Create `L2OrderBook` model to represent the current market depth in `src/main/java/com/arbitrage/engine/core/models/`.
- [x] T010 Implement the "Walk the Book" VWAP algorithm in `src/main/java/com/arbitrage/engine/core/VwapCalculator.java`.
- [x] T011 [P] Implement `SlippageGuard` to compare Calculated VWAP vs. Target Price in `src/main/java/com/arbitrage/engine/risk/SlippageGuard.java`.
- [x] T012 [P] Create unit tests for `VwapCalculator` covering empty book, insufficient depth, and multi-level fills in `src/test/java/com/arbitrage/engine/core/VwapCalculatorTest.java`.
- [x] T013 [P] Create unit tests for `SlippageGuard` with precise `BigDecimal` comparisons in `src/test/java/com/arbitrage/engine/risk/SlippageGuardTest.java`.

**Checkpoint**: Core math and risk logic verified - ready for integration.

---

## Phase 2: Integration (P2: gRPC Server & Dual-DB Integration)

**Purpose**: Connecting the brain to the muscle and ensuring auditability.

### User Story 1 - Successful Institutional-Grade Execution (Priority: P1)

- [x] T014 Implement `ExecutionService` gRPC server handler in `src/main/java/com/arbitrage/engine/api/ExecutionServiceImpl.java`.
- [x] T015 Setup R2DBC connection pool and `TradeLedgerRepository` in `src/main/java/com/arbitrage/engine/persistence/`.
- [x] T016 Setup Lettuce Redis client for in-flight order tracking in `src/main/java/com/arbitrage/engine/persistence/RedisOrderSync.java`.
- [x] T017 [US1] Implement main execution flow: Receive gRPC -> Walk Book -> Check Slippage -> Persist Audit (Async) -> Return Result.
- [x] T018 [P] [US1] Integration test: End-to-end execution flow using Testcontainers for PostgreSQL in `src/test/java/com/arbitrage/engine/integration/ExecutionIntegrationTest.java`.

### User Story 2 - Automated Slippage Veto (Priority: P2)

- [x] T019 [US2] Integrate `SlippageGuard` into the `ExecutionService` flow.
- [x] T020 [US2] Ensure rejections are logged to `trade_ledger` with `STATUS_REJECTED_SLIPPAGE`.
- [x] T021 [P] [US2] Integration test: Trigger slippage veto and verify DB record in `src/test/java/com/arbitrage/engine/integration/SlippageVetoTest.java`.

### User Story 3 - Stale Alpha Protection (Priority: P3)

- [x] T022 [US3] Implement TTL validation logic using `timestamp_ns` from the gRPC request.
- [x] T023 [US3] Ensure late requests return `STATUS_REJECTED_LATENCY` and are logged.
- [x] T024 [P] [US3] Integration test: Verify timeout for stale requests in `src/test/java/com/arbitrage/engine/integration/LatencyProtectionTest.java`.

---

## Phase 3: Polish & Cross-Cutting Concerns

- [x] T025 [P] Implement Micrometer metrics for P99 latency tracking of the execution loop.
- [x] T026 [P] Add structured logging with request correlation IDs for easier debugging.
- [x] T027 [P] Final validation against `quickstart.md` instructions.
- [x] T028 [P] Run `cli_audit.py` to ensure project health and pattern compliance.

---

## Dependencies & Execution Order

1.  **Phase 0 (Setup)**: MUST be completed first to provide the build environment and generated gRPC classes.
2.  **Phase 1 (Core)**: Can run in parallel with Setup (except for T010/T011 which need the model).
3.  **Phase 2 (Integration)**: Depends on Phase 0 (gRPC) and Phase 1 (Core).
4.  **Polish**: Final step.

---

## Implementation Strategy: TDD & Virtual Threads

*   **Virtual Threads**: Configure the gRPC Netty server to use a Virtual Thread executor for handling RPC calls to ensure non-blocking scalability.
*   **Precision**: Every task involving money MUST use `BigDecimal`. `double` is only allowed for the gRPC message layer before conversion.
*   **Auditability**: Every outcome (Success/Fail) MUST be persisted to PostgreSQL before the gRPC response is returned to the Brain.
