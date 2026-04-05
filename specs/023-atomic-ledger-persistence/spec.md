# Feature Specification: Atomic Idempotency, State Rollback, and Blocking Ledger Persistence

**Feature Branch**: `023-atomic-ledger-persistence`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "feature="Atomic Idempotency, State Rollback, and Blocking Ledger Persistence" context="execution-engine/src/main/java/com/arbitrage/engine/api/ExecutionServiceImpl.java,execution-engine/src/main/java/com/arbitrage/engine/persistence/RedisOrderSync.java" requirements="1. Replace read-then-write idempotency with atomic SETNX/Lua script. 2. Implement guaranteed Redis state cleanup (SUCCESS/FAILED/REJECTED) in a finally block. 3. Replace reactive .subscribe() on database writes with transactional, blocking writes or guaranteed dead-letter queues before returning gRPC success.""

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Prevent Duplicate Order Processing (Priority: P1)

As a trader, I want to ensure that my orders are never processed more than once, even if I send the same request multiple times due to network retries or client-side errors, so that I don't double my risk or lose capital.

**Why this priority**: Preventing duplicate execution is the most critical safety requirement for a trading bot.

**Independent Test**: Simulate 10 simultaneous identical order requests. Only one should result in an actual trade execution, while the others should be rejected as duplicates.

**Acceptance Scenarios**:

1. **Given** no previous order with ID "ORD-123", **When** an order request "ORD-123" is received, **Then** it is processed successfully.
2. **Given** order "ORD-123" is currently being processed or has been processed, **When** another request with "ORD-123" is received, **Then** the second request is rejected immediately without secondary processing.

---

### User Story 2 - Guaranteed State Cleanup (Priority: P2)

As a system administrator, I want the bot to always leave the system in a consistent state (SUCCESS, FAILED, or REJECTED), even if an unexpected error occurs during order execution, so that I don't have "stuck" orders or locked resources.

**Why this priority**: Inconsistent state in Redis can block future orders or cause the bot to think it has more open positions than it actually does.

**Independent Test**: Trigger a hard exception (e.g., NullPointerException) during the middle of the execution flow. Verify that the Redis state for that order is still updated to "FAILED" instead of remaining in "IN_PROGRESS".

**Acceptance Scenarios**:

1. **Given** an order is marked as "IN_PROGRESS" in Redis, **When** the execution fails due to a system error, **Then** the state is updated to "FAILED" in the cleanup block.
2. **Given** an order is marked as "IN_PROGRESS" in Redis, **When** the execution completes successfully, **Then** the state is updated to "SUCCESS".

---

### User Story 3 - Reliable Ledger Persistence (Priority: P1)

As a trader, I want to be 100% sure that if the bot tells me an order was successful, that order has actually been recorded in the permanent ledger, so that I can reconcile my trades and rely on the bot's reporting.

**Why this priority**: If a gRPC call returns success but the database write fails silently (e.g., due to an async fire-and-forget failure), the user loses trust in the system's audit trail.

**Independent Test**: Mock the database to be slow or fail. Ensure the gRPC response is either delayed until the write succeeds or returns an error if the write fails.

**Acceptance Scenarios**:

1. **Given** a successful trade execution, **When** the ledger persistence is still in progress, **Then** the gRPC response is held back.
2. **Given** a successful trade execution, **When** the ledger persistence fails, **Then** the gRPC response returns an error status instead of "OK".

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST use an atomic operation (SETNX or Lua script) to check and set the idempotency lock in Redis.
- **FR-002**: System MUST guarantee that the order state in Redis is updated to a terminal status (SUCCESS, FAILED, or REJECTED) regardless of execution outcome.
- **FR-003**: System MUST perform ledger persistence as a blocking operation that completes before the final gRPC response is sent.
- **FR-004**: System MUST NOT return a gRPC "OK" status if the ledger entry has not been successfully persisted or queued in a guaranteed dead-letter system.
- **FR-005**: System MUST ensure no data loss via a mandatory Dead-Letter Queue (DLQ) if the terminal state cannot be persisted to the primary ledger.

### Key Entities

- **Order**: Represents the intent to trade, identified by a unique ID.
- **Idempotency Lock**: A Redis entry that prevents multiple threads from processing the same Order ID simultaneously.
- **Ledger Entry**: The permanent record of a completed (or failed) trade execution in the persistent database.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero occurrences of duplicate trades for the same Order ID under high-concurrency stress testing (100+ parallel identical requests).
- **SC-002**: 100% of initiated orders reach a terminal state (SUCCESS/FAILED/REJECTED) in Redis within 30 seconds of execution start.
- **SC-003**: 0% discrepancy between "Success" gRPC responses and existing records in the persistent ledger.
- **SC-004**: System recovers 100% of "stuck" order locks via the mandatory cleanup block without manual intervention.

## Assumptions

- [Assumption about environment]: Redis is available and configured with persistence (AOF/RDB) to prevent lock loss on restart.
- [Assumption about scope]: This feature focuses on the Execution Engine (Java) and does not modify the Frontend or Python Trading Bot logic beyond gRPC response handling.
- [Assumption about data]: The database used for ledger persistence supports ACID transactions or blocking writes.
