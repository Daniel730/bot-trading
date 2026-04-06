# Tasks: Shadow Mode Paper Trading

**Feature Branch**: `026-shadow-mode-paper-trading`  
**Created**: 2026-04-06  
**Status**: Draft  
**Plan**: [specs/026-shadow-mode-paper-trading/plan.md]

## Implementation Strategy

We will implement Shadow Mode by first setting up the global environment toggle (`DRY_RUN`), then creating a `MockBroker` that implements the same interface as our live brokers. The final step involves updating the persistence layer to tag these trades correctly. This ensures that the entire "brain" and "muscle" validation logic remains active while swapping only the final execution leg.

## Phase 1: Setup

- [X] T001 Initialize feature directory and verify `DRY_RUN` configuration requirements in `src/main/resources/application.yml`
- [X] T002 Update `EnvironmentConfig.java` to support the `DRY_RUN` flag in `execution-engine/src/main/java/com/arbitrage/engine/config/EnvironmentConfig.java`

## Phase 2: Foundational

- [X] T003 [P] Define `ExecutionMode` enum (LIVE, PAPER) in `execution-engine/src/main/java/com/arbitrage/engine/core/models/ExecutionMode.java`
- [X] T004 [P] Create `Broker` interface if not already abstracted in `execution-engine/src/main/java/com/arbitrage/engine/broker/Broker.java`
- [X] T005 Refactor `ExecutionServiceImpl.java` to use the `Broker` interface in `execution-engine/src/main/java/com/arbitrage/engine/api/ExecutionServiceImpl.java`

## Phase 3: [US1] Risk-Free Strategy Validation (Priority: P1)

**Story Goal**: Implement the `MockBroker` that simulates fills using L2 OrderBook depth.

- [X] T006 [P] [US1] Implement `MockBroker` with "Walk the Book" fill logic in `execution-engine/src/main/java/com/arbitrage/engine/broker/MockBroker.java`
- [X] T007 [US1] Integrate `MockBroker` with `L2FeedService` for real-time depth data in `execution-engine/src/main/java/com/arbitrage/engine/broker/MockBroker.java`
- [X] T008 [US1] Implement stale data check for L2 snapshots in `execution-engine/src/main/java/com/arbitrage/engine/broker/MockBroker.java` (Reject if older than 100ms)
- [X] T009 [US1] Create unit tests for `MockBroker` fill calculation (including slippage and stale data) in `execution-engine/src/test/java/com/arbitrage/engine/broker/MockBrokerTest.java`

## Phase 4: [US2] Operational Safety Guard (Priority: P2)

**Story Goal**: Implement the `BrokerageRouter` logic to intercept and route trades based on `DRY_RUN`.

- [X] T010 [US2] Implement `BrokerageRouter` factory to select either `LiveBroker` or `MockBroker` in `execution-engine/src/main/java/com/arbitrage/engine/broker/BrokerageRouter.java`
- [X] T011 [US2] Add logging to `BrokerageRouter` to clearly signal "Shadow Mode Active" when routing to `MockBroker` in `execution-engine/src/main/java/com/arbitrage/engine/broker/BrokerageRouter.java`
- [X] T012 [US2] Verify end-to-end routing with integration tests in `execution-engine/src/test/java/com/arbitrage/engine/integration/ShadowModeIntegrationTest.java`

## Phase 5: Polish & Cross-cutting Concerns

- [X] T013 Update `TradeLedgerRepository` to persist the `execution_mode` and `reasoning_metadata` flags in `execution-engine/src/main/java/com/arbitrage/engine/persistence/TradeLedgerRepository.java`
- [X] T014 Update `TradeAudit` model to include `execution_mode` and `reasoning_metadata` fields for "Thought Journal" alignment in `execution-engine/src/main/java/com/arbitrage/engine/persistence/models/TradeAudit.java`
- [X] T015 Benchmark Shadow Mode latency to verify <100ms per multi-leg request (SC-004)
- [X] T016 Run full integration test suite with `DRY_RUN=true` to ensure zero real exchange calls occur.

## Dependencies

1. US1 depends on Phase 1 & 2.
2. US2 depends on US1.
3. Polish depends on US2.

## Parallel Execution Examples

- **Example 1**: T003, T004, and T006 can be worked on concurrently as they define new models/interfaces.
- **Example 2**: T008 (tests) and T006 (implementation) can be developed in parallel if the interface is stable.
