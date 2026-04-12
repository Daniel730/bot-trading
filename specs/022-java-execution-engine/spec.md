# Feature Specification: High-Performance Execution Engine (The Muscle)

**Feature Branch**: `022-java-execution-engine`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "\ goal="Implement Java High-Performance Execution Engine (The Muscle)" \ context="Python Brain calculates Alpha; Java Engine validates L2 Liquidity and executes. Integration via gRPC. Dual-DB architecture (PostgreSQL for audits, Redis for in-flight state)." \ constraints="Use Java 21 Virtual Threads; BigDecimal for all math; <2ms internal latency; R2DBC for async PostgreSQL; Strict Protobuf contract enforcement; 'Walk the Book' VWAP logic mandatory." \ outcomes="spec.md, data-model.md, gRPC-contract.proto, tasks.md""

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Successful Institutional-Grade Execution (Priority: P1)

As a Quantitative Trader, I want the system to execute arbitrage signals with guaranteed slippage protection so that the realized profit matches the theoretical alpha.

**Why this priority**: This is the core function of the execution layer. Without reliable execution that respects liquidity, the bot will lose money to market friction.

**Independent Test**: Can be tested by sending an execution request with a quantity that fits within the top levels of a mock L2 book. The system should return a success response and create a record in the persistent trade ledger.

**Acceptance Scenarios**:

1. **Given** a valid L2 order book with ample liquidity, **When** a BUY request for 10 shares arrives with a `max_slippage_pct` of 0.1%, **Then** the system should calculate a VWAP within the limit, execute the trade, and return a success status.
2. **Given** a completed execution, **When** checking the persistent database, **Then** there must be an entry in the trade ledger with the exact signal identifier and calculated VWAP.

---

### User Story 2 - Automated Slippage Veto (Priority: P2)

As a Risk Manager, I want the execution engine to "veto" any trade where the market liquidity has thinned out since the signal was generated, so that we avoid "buying the top" of a shallow book.

**Why this priority**: High-frequency arbitrage is sensitive to small price movements. This guard prevents the bot from executing losing trades during high volatility.

**Independent Test**: Can be tested by sending a request for a large quantity against a "thin" mock L2 book. The system should return a risk limit rejection.

**Acceptance Scenarios**:

1. **Given** an L2 book where the VWAP for 50 shares is $100.15, **When** a request arrives with a target of $100.00 and `max_slippage_pct` of 0.1%, **Then** the system must reject the trade.
2. **Given** a rejected trade, **When** checking the logs, **Then** the reason must be explicitly stated as a slippage violation with the calculated vs. allowed values.

---

### User Story 3 - Stale Alpha Protection (Priority: P3)

As a System Administrator, I want the execution engine to ignore requests that arrive too late due to network or processing lag, so that we don't execute on "stale" market conditions.

**Why this priority**: Arbitrage opportunities often exist for only tens of milliseconds. Executing late is high-risk.

**Independent Test**: Can be tested by sending a request with a timestamp that is significantly in the past.

**Acceptance Scenarios**:

1. **Given** a request with a time-to-live (TTL) of 50ms, **When** the message arrives after the TTL has expired, **Then** the system must discard the request and log a latency timeout warning.

---

### Edge Cases

- **Insufficient Liquidity**: What happens when the total quantity available in the entire L2 book is less than the requested quantity? (The system must reject the trade with an insufficient depth reason).
- **Partial Fills**: How does the system handle a broker rejection of one leg in a multi-leg trade? (The system must attempt to cancel or reverse other related legs and log a critical asymmetry error).
- **Restart Recovery**: How does the system handle orders that were active during a service interruption? (The system must reconcile the status of all interrupted orders with the external broker upon startup).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST implement a high-performance, low-latency communication interface to receive execution requests from the signal generator.
- **FR-002**: System MUST validate the freshness of every request against a configurable maximum age (default 50ms).
- **FR-003**: System MUST calculate the Volume-Weighted Average Price (VWAP) for the requested quantity by "walking" the Level 2 (L2) order book.
- **FR-004**: System MUST enforce a hard maximum slippage constraint; any trade where the calculated VWAP exceeds the allowed slippage threshold MUST be rejected.
- **FR-005**: System MUST use high-precision arithmetic for all financial calculations (Price, Quantity, VWAP) to maintain at least 10-decimal precision.
- **FR-006**: System MUST persist every execution attempt, result, and latency metric to a persistent record store using non-blocking connectivity.
- **FR-007**: System MUST synchronize active order states with a transient data store to prevent duplicate executions and enable crash recovery.
- **FR-008**: System MUST support multi-leg atomic execution for related asset pairs.

### Key Entities *(include if feature involves data)*

- **ExecutionRequest**: A structured request containing signal identification, asset identifiers, execution legs (side, quantity, target price), and risk constraints.
- **TradeLedger**: A persistent record of every trade attempt (success or failure) linked to the originating signal.
- **OrderState**: The real-time status of an active order (e.g., Sent, Pending, Filled, Canceled).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Internal processing latency (from request receipt to order submission) is under **2ms** for 99% of requests.
- **SC-002**: 100% of executed trades have a realized slippage equal to or less than the requested threshold.
- **SC-003**: Zero precision loss in fractional share calculations (verified against 6-decimal standard).
- **SC-004**: System successfully reconstructs the state of all pending orders within **1 second** of service restart.

## Assumptions

- **Market Data Feed**: A low-latency Level 2 market data feed is available and integrated into the engine's memory space.
- **Clock Synchronization**: Host environments have synchronized clocks to ensure timestamp-based validation is accurate.
- **Infrastructure Availability**: Persistent and transient data stores are operational and reachable via the internal network.
- **Broker Interface**: The external broker interface supports asynchronous submission and status reconciliation.
