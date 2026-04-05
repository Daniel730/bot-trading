# Feature Specification: Atomic Multi-Leg Execution

**Feature Branch**: `025-atomic-multi-leg-execution`  
**Created**: 2026-04-06  
**Status**: Draft  
**Input**: User description: "feature="025-atomic-multi-leg-execution" context="execution-engine/src/main/java/com/arbitrage/engine/api/ExecutionServiceImpl.java,execution-engine/src/main/java/com/arbitrage/engine/persistence/TradeLedgerRepository.java" requirements="1. Remove the MVP single-leg logic. 2. Iterate through all ExecutionLegs in the gRPC request. 3. Calculate VWAP and validate Slippage/Depth for ALL legs before routing to the broker. 4. Reject the entire ExecutionRequest if any single leg fails validation (All-or-Nothing). 5. Update TradeLedgerRepository and audit logging to persist multi-leg executions accurately.""

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Atomic Paired Trade Execution (Priority: P1)

As a quantitative trader, I want my paired arbitrage trades to execute both legs simultaneously or not at all, so that I avoid naked directional exposure and preserve capital during market volatility.

**Why this priority**: This is the core requirement for statistical arbitrage. Without atomicity, the system is gambling rather than performing arbitrage, posing a critical risk to capital.

**Independent Test**: Can be fully tested by submitting a 2-leg request where both legs meet risk parameters and verifying that both are processed and logged as successful.

**Acceptance Scenarios**:

1. **Given** a valid 2-leg arbitrage request (e.g., BUY KO, SELL PEP), **When** both legs pass VWAP and slippage validation, **Then** both legs should proceed to the broker and be logged in the trade ledger.
2. **Given** a valid multi-leg request, **When** the system calculates market depth, **Then** it must ensure sufficient depth exists for *all* legs before approving the trade.

---

### User Story 2 - All-or-Nothing Validation Failure (Priority: P1)

As a risk manager, I want the system to reject an entire trade request if even one leg fails validation, so that I never end up with a partial, unhedged position.

**Why this priority**: Essential for risk mitigation. A partial fill or single-leg execution in an arbitrage strategy creates "leg risk," which can lead to significant losses.

**Independent Test**: Can be tested by submitting a 2-leg request where the first leg is valid but the second leg violates slippage limits, verifying that the entire request is rejected.

**Acceptance Scenarios**:

1. **Given** a 2-leg request where Leg A is valid but Leg B has insufficient market depth, **When** the execution engine validates the request, **Then** the status must be REJECTED_DEPTH and *neither* leg should be sent to the broker.
2. **Given** a 2-leg request where Leg A is valid but Leg B exceeds the maximum slippage, **When** the execution engine validates the request, **Then** the status must be REJECTED_SLIPPAGE and the entire request must fail.

---

### User Story 3 - Multi-Leg Audit Transparency (Priority: P2)

As a compliance officer, I want to see the detailed execution state of every leg in a trade request, including failed ones, so that I can audit why specific arbitrage opportunities were rejected.

**Why this priority**: Necessary for debugging strategy performance and ensuring institutional-grade transparency in the execution pipeline.

**Independent Test**: Can be tested by submitting a multi-leg trade and verifying that the `trade_ledger` table contains one record per leg with consistent `signal_id` and accurate `status`.

**Acceptance Scenarios**:

1. **Given** a rejected 2-leg trade request, **When** I query the trade ledger by `signal_id`, **Then** I should see two records reflecting the state of both legs at the time of rejection.

---

### Edge Cases

- **Mixed Side Legs**: What happens when a request contains two BUY legs or two SELL legs? (System should process them atomically based on their individual side parameters).
- **Latency Spikes**: How does the system handle a latency timeout that occurs after validating the first leg but before the second? (The latency check should happen at the start of the request processing to ensure atomicity).
- **Partial Persistence Failure**: How does the system handle a database error when saving the second leg's audit after the first succeeded? (Audits should be saved in a batch/transaction to ensure ledger consistency).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST iterate through all `ExecutionLegs` provided in a gRPC `ExecutionRequest`.
- **FR-002**: System MUST calculate the Volume Weighted Average Price (VWAP) for every leg independently using the latest L2 order book.
- **FR-003**: System MUST validate each leg against the global `max_slippage_pct` and available market depth before any leg is routed for execution.
- **FR-004**: System MUST implement "All-or-Nothing" logic: if any single leg fails validation, the entire `ExecutionRequest` MUST be rejected.
- **FR-005**: System MUST persist an audit record for every leg in the `trade_ledger`, sharing the same `signal_id` to maintain relationship context.
- **FR-006**: System MUST record the `actual_vwap` and `status` for all legs in the audit trail, even in the event of a validation rejection.
- **FR-007**: System MUST provide the `actual_vwap` of the primary leg (index 0) in the `ExecutionResponse` for backward compatibility with existing reporting.

### Key Entities *(include if feature involves data)*

- **ExecutionRequest**: The atomic container for a multi-leg trade, identified by a unique `signal_id`.
- **ExecutionLeg**: A single component of a trade (Ticker, Side, Quantity, Target Price).
- **TradeLedger**: The persistent audit log where each leg's execution attempt is recorded.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of multi-leg trade requests are handled atomically (either all legs pass validation or the entire request is rejected).
- **SC-002**: The `trade_ledger` consistently contains $N$ records for a request with $N$ legs, with zero "orphaned" or missing leg records.
- **SC-003**: Validation latency for a 2-leg trade remains under 5ms (excluding network I/O).
- **SC-004**: Zero "naked directional" trades are executed by the engine when a multi-leg request is partially invalid.

## Assumptions

- **Ordered Legs**: It is assumed that the first leg in the request (index 0) is the "primary" leg for response reporting purposes.
- **Uniform Slippage**: The `max_slippage_pct` provided in the request applies globally to all legs.
- **Broker Atomicity**: While this feature ensures internal validation atomicity, it assumes the downstream broker integration will handle the actual order routing (to be implemented in a future feature).
- **Consistent Tickers**: It is assumed that L2 market data is available for all tickers requested in the legs.
