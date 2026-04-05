# Implementation Plan: Atomic Ledger Persistence

**Feature Branch**: `023-atomic-ledger-persistence`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: [specs/023-atomic-ledger-persistence/spec.md]

## Technical Context

- **Tech Stack**: Java 21, Spring Boot (optional), gRPC, Redis (Lettuce), PostgreSQL (R2DBC).
- **Concurrency Model**: Java Virtual Threads (Loom) are used for gRPC calls.
- **Constraints**: 
  - MUST NOT block virtual threads for too long (e.g., waiting for slow DB).
  - MUST ensure Redis cleanup in a `finally` block or equivalent reactive construct.
- **Dependencies**: 
  - `io.lettuce:lettuce-core` for Redis.
  - `io.r2dbc:r2dbc-postgresql` for DB access.

## Constitution Check

- **Principle I: Prioridade à Preservação de Capital**: Idempotency is crucial to prevent double-spending or over-exposure.
- **Principle III: Auditabilidade Total**: Guaranteed ledger persistence ensures we have a complete audit trail of every execution attempt.
- **Principle IV: Operação Estrita**: All operations must respect market hours (already enforced in high-level bot).

## Research Summary

- **Lua for Atomicity**: Confirmed. Use `EVAL` with the custom script to check and set the idempotency key in one step. TTL is set to 5 minutes as a catastrophic fallback.
- **Blocking vs Reactive**: We will use R2DBC's `Mono.toFuture().get()` or `block()` cautiously within the virtual thread to ensure the response is not sent before the write is confirmed.
- **DLQ Strategy**: If the primary ledger fails, the record will be pushed to a specific, strictly-typed Redis list named `dlq:execution:audit_ledger`.

## Implementation Strategy

### Phase 1: Data Model & Contracts
- [x] Defined Redis key structure for idempotency locks (5m TTL).
- [x] Defined specific DLQ structure in Redis (`dlq:execution:audit_ledger`).
- [x] Defined PostgreSQL schema for trade_ledger.

### Phase 2: Core Logic Implementation
- **Step 1: Update RedisOrderSync**:
  - Implement `checkAndSetIdempotency(UUID signalId)` using the Lua script with a 5-minute TTL.
  - Implement `updateStatus(UUID signalId, String status)`.
- **Step 2: Update TradeLedgerRepository**:
  - Update `saveAudit` to be blocking or return a `Mono` that must be waited on.
  - Implement a fallback mechanism to push to `dlq:execution:audit_ledger` on DB error.
- **Step 3: Refactor ExecutionServiceImpl**:
  - Replace the current "exists check + then set" with the atomic `checkAndSetIdempotency`.
  - Wrap the execution logic in a `try-finally` block to ensure Redis state is always updated to a terminal state (SUCCESS, REJECTED, FAILED).
  - Ensure the gRPC `responseObserver.onNext()` only happens AFTER `saveAudit` completes.

### Phase 3: Verification & Integration
- [ ] Unit tests for the Lua script using a mocked Redis container.
- [ ] Integration tests simulating DB failures and verifying `dlq:execution:audit_ledger` population.
- [ ] Stress tests for high-concurrency idempotency.

## Technical Unknowns

(None. All architectural boundaries are locked.)
