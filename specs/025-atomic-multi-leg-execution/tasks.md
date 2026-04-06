# Tasks: Atomic Multi-Leg Execution

**Input**: Design documents from `/specs/025-atomic-multi-leg-execution/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

## Phase 1: Foundational (Blocking Prerequisites)

- [X] T001 [P] Define `TradeAudit` record in `execution-engine/src/main/java/com/arbitrage/engine/persistence/TradeLedgerRepository.java`
- [X] T002 Implement `saveAudits` batching logic in `TradeLedgerRepository.java` using R2DBC `statement.add()`
- [X] T003 [P] Refactor `saveAudit` to delegate to `saveAudits` for backward compatibility

## Phase 2: User Story 1 - Atomic Paired Trade Execution (Priority: P1) 🎯 MVP

**Goal**: Ensure both legs of a paired trade execute or none do.

**Independent Test**: Submit a valid 2-leg request and verify both are logged as SUCCESS.

### Implementation for User Story 1

- [X] T004 [US1] Refactor `executeTrade` in `ExecutionServiceImpl.java` to iterate through all legs in the request.
- [X] T005 [US1] Implement the "Validation Phase" to calculate VWAP and check slippage/depth for ALL legs before execution.
- [X] T006 [US1] Implement the "Execution Phase" to only proceed if all validations pass.
- [X] T007 [US1] Update successful audit persistence to use `saveAudits` for all validated legs.

## Phase 3: User Story 2 - All-or-Nothing Validation Failure (Priority: P1)

**Goal**: Reject the entire request if any single leg fails validation.

**Independent Test**: Submit a 2-leg request where one leg fails slippage, verify entire request is REJECTED.

### Tests for User Story 2

- [X] T008 [US2] Add `testExecuteTrade_MultiLeg_AtomicFailure` to `execution-engine/src/test/java/com/arbitrage/engine/integration/ExecutionIntegrationTest.java`

### Implementation for User Story 2

- [X] T009 [US2] Update `handleError` in `ExecutionServiceImpl.java` to persist "REJECTED" audits for ALL legs in the original request.
- [X] T010 [US2] Ensure all exception types (Slippage, Depth, Latency) trigger the atomic rejection flow.

## Phase 4: User Story 3 - Multi-Leg Audit Transparency (Priority: P2)

**Goal**: Detailed audit state for every leg in the ledger.

**Independent Test**: Query `trade_ledger` after a multi-leg trade and verify $N$ rows exist for $N$ legs.

### Implementation for User Story 3

- [X] T011 [US3] Verify `actual_vwap` and `status` are correctly recorded for failed legs in the ledger.

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T012 [P] Documentation updates in `quickstart.md` with multi-leg `grpcurl` examples.
- [X] T013 Verify backward compatibility: `ExecutionResponse` returns `actual_vwap` of the first leg.
- [ ] T014 [P] [SC-003] Verify validation latency is < 5ms for 2-leg trades using Micrometer metrics or execution logs.

---

## Dependencies & Execution Order

- **Foundational (Phase 1)**: MUST be complete before US1/US2.
- **US1 & US2**: Are tightly coupled in the `executeTrade` refactor; should be implemented together.
- **US3**: Verified during US1/US2 testing.
- **Polish**: Final validation.
