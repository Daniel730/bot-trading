# Tasks: Atomic Ledger Persistence (023-atomic-ledger-persistence)

**Input**: Design documents from `/specs/023-atomic-ledger-persistence/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Database schema and basic configuration

- [X] T001 Create PostgreSQL migration for `trade_ledger` table in `execution-engine/src/main/resources/db/migration/V1__Create_Trade_Ledger.sql` (if not already present)
- [X] T002 [P] Define Redis DLQ key `dlq:execution:audit_ledger` in a central configuration or constant file

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure for atomic Redis operations and blocking persistence

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Implement Lua script for atomic `checkAndSetIdempotency` in `RedisOrderSync.java`
- [X] T004 Implement `updateStatus` method in `RedisOrderSync.java` for terminal state updates
- [X] T005 [P] Setup error handling and DLQ push logic in `TradeLedgerRepository.java`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Prevent Duplicate Order Processing (Priority: P1) 🎯 MVP

**Goal**: Ensure no trade is executed twice using atomic Redis operations.

**Independent Test**: Simulate 10 simultaneous identical order requests. Only one should succeed; others must be rejected as duplicates.

### Tests for User Story 1

- [X] T006 [P] [US1] Unit test for `RedisOrderSync.checkAndSetIdempotency` with Lua script in `execution-engine/src/test/java/com/arbitrage/engine/persistence/RedisOrderSyncTest.java`
- [ ] T007 [US1] High-concurrency stress test (100+ parallel requests) for `ExecutionServiceImpl.executeTrade` in `execution-engine/src/test/java/com/arbitrage/engine/api/ExecutionServiceImplConcurrencyTest.java`

### Implementation for User Story 1

- [X] T008 [US1] Replace current "exists then mark" logic in `ExecutionServiceImpl.executeTrade` with atomic `redisSync.checkAndSetIdempotency(signalId)`
- [X] T009 [US1] Ensure `ExecutionServiceImpl` returns the cached status for duplicate requests correctly

**Checkpoint**: User Story 1 (Atomic Idempotency) fully functional and testable independently

---

## Phase 4: User Story 3 - Reliable Ledger Persistence (Priority: P1)

**Goal**: Guarantee audit trails exist for every "Success" gRPC response.

**Independent Test**: Mock DB failure and verify gRPC returns error while audit payload is found in Redis DLQ.

### Tests for User Story 3

- [ ] T010 [P] [US3] Unit test for `TradeLedgerRepository.saveAudit` with DLQ fallback in `execution-engine/src/test/java/com/arbitrage/engine/persistence/TradeLedgerRepositoryTest.java`
- [ ] T011 [US3] Integration test verifying gRPC blocking until DB write is confirmed or failed

### Implementation for User Story 3

- [X] T012 [US3] Update `TradeLedgerRepository.saveAudit` to ensure blocking execution or guaranteed completion before the gRPC response is sent
- [X] T013 [US3] Implement DLQ fallback logic in `TradeLedgerRepository` to push to `dlq:execution:audit_ledger` if PostgreSQL is unavailable
- [X] T014 [US3] Refactor `ExecutionServiceImpl.executeTrade` to block/wait on `repository.saveAudit` before calling `responseObserver.onNext()`

**Checkpoint**: User Story 3 (Blocking Persistence) fully functional and testable independently

---

## Phase 5: User Story 2 - Guaranteed State Cleanup (Priority: P2)

**Goal**: Always leave Redis in a terminal state (SUCCESS, FAILED, or REJECTED) even on crashes/exceptions.

**Independent Test**: Trigger a hard exception during execution and verify Redis state is updated to `FAILED` instead of remaining `PENDING`.

### Tests for User Story 2

- [ ] T015 [P] [US2] Integration test for exception handling and Redis state cleanup in `execution-engine/src/test/java/com/arbitrage/engine/api/ExecutionServiceImplCleanupTest.java`

### Implementation for User Story 2

- [X] T016 [US2] Refactor `ExecutionServiceImpl.executeTrade` with a `try-finally` block to ensure `redisSync.updateStatus` is always called
- [X] T017 [US2] Map all internal exceptions to appropriate terminal states (e.g., `SlippageViolation` -> `REJECTED_SLIPPAGE`) in the cleanup block

**Checkpoint**: User Story 2 (State Cleanup) fully functional and testable independently

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and final validation

- [X] T018 [P] Update `docs/agents.md` with new idempotency and persistence guarantees
- [ ] T019 Run `quickstart.md` validation on the completed implementation
- [ ] T020 [P] Verify performance impact of blocking writes under load

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup & Foundational (Phase 1 & 2)**: BLOCKS all user stories. Must be completed first.
- **User Stories (Phase 3, 4, 5)**: Depend on Phase 1 & 2. US1 and US3 have Priority P1 (High), US2 has Priority P2 (Medium).
- **Polish (Phase 6)**: Final step.

### Parallel Opportunities

- T006, T007, T010, T011, T015 (Tests) can be developed in parallel with their respective implementations.
- US1, US3, and US2 can be implemented in parallel once Phase 2 is complete.

---

## Implementation Strategy

### MVP First (P1 Stories)

1. Complete Setup + Foundational.
2. Complete US1 (Atomic Idempotency) -> Prevents double spending.
3. Complete US3 (Reliable Ledger) -> Ensures auditability.
4. **STOP and VALIDATE**: Verify atomic execution and blocking persistence.

### Incremental Delivery

1. Add US2 (Guaranteed Cleanup) -> Improves system stability.
2. Complete Polish tasks.
