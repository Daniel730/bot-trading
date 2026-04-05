# Feature Specification: Execution and Risk Microservice with Database Migration

**Feature Branch**: `019-execution-service-db-migration`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "Create a new architecture specification defining a Java-based Execution and Risk Microservice. This Java service will expose a gRPC port to the existing Python LLM Brain. It must handle Level 2 Order Book VWAP calculations, maintain HTTP Keep-Alive pools for the brokerage API, and manage the Redis state. The Python layer will be stripped of execution responsibilities and relegated entirely to strategy calculation and agent orchestration. 2. Isolate the Database Transition: Update the data model specification to migrate away from SQLite. Define a strictly transient Redis schema for Kalman filter states and rate-limit counters, and a robust PostgreSQL schema using connection pooling for historical trades and telemetry logs. By decoupling the architecture in this way, you allow the Python LLMs to think deeply and asynchronously, while a high-performance compiled language handles the microsecond realities of the order book."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Low-Latency Order Execution (Priority: P1)

As a quantitative trader, I want the system to execute orders based on Level 2 market data with microsecond precision so that I can capture alpha from transient market inefficiencies.

**Why this priority**: This is the core value proposition of the architectural shift—moving execution to a compiled language (Java) to handle high-frequency data.

**Independent Test**: Can be tested by simulating a Level 2 order book feed and verifying that the Java service calculates VWAP and issues execution commands significantly faster than the legacy Python implementation.

**Acceptance Scenarios**:

1. **Given** a high-volume Level 2 order book stream, **When** a trade signal is received via gRPC, **Then** the Java service MUST calculate the VWAP and dispatch the order within < 5ms.
2. **Given** a connection to the brokerage API, **When** multiple orders are dispatched, **Then** the service MUST reuse existing HTTP Keep-Alive connections to minimize handshake latency.

---

### User Story 2 - Distributed Strategy Orchestration (Priority: P2)

As an AI Agent developer, I want to use Python for complex reasoning and strategy calculation while delegating the technical "heavy lifting" of execution to a specialized service so that the LLM brain isn't blocked by I/O or low-level calculations.

**Why this priority**: Enables the scaling of the "brain" (Python) independently of the "body" (Java execution).

**Independent Test**: Can be tested by running a Python strategy agent that sends gRPC requests to a mock Java execution service and verifying successful command delivery and state synchronization.

**Acceptance Scenarios**:

1. **Given** a Python strategy agent, **When** it identifies a trade opportunity, **Then** it MUST be able to send an execution request via gRPC and receive a transaction ID immediately.
2. **Given** a change in strategy parameters, **When** the Python agent updates the target state, **Then** the Java service MUST reflect this in its Redis-managed transient state.

---

### User Story 3 - Robust Data Persistence and Recovery (Priority: P3)

As a system administrator, I want historical trades and telemetry to be stored in a robust, pooled PostgreSQL database while transient states are kept in Redis so that the system is both performant and resilient to crashes.

**Why this priority**: Ensures long-term data integrity and system stability during high-load periods.

**Independent Test**: Can be tested by performing a bulk insert of telemetry logs and verifying PostgreSQL connection pooling efficiency, and by restarting the Java service and verifying Redis state restoration.

**Acceptance Scenarios**:

1. **Given** a high frequency of trade events, **When** the system logs telemetry, **Then** it MUST use a PostgreSQL connection pool to avoid connection overhead.
2. **Given** a service crash, **When** the Java service restarts, **Then** it MUST recover Kalman filter states and rate-limit counters from Redis within < 1 second.

---

### Edge Cases

- **gRPC Connection Loss**: How does the system handle a disconnect between the Python brain and the Java execution service? (Fallback: Java service should enter a "safety mode" and cancel active synthetic stops if the brain is unresponsive).
- **Brokerage API Rate Limiting**: How does the Java service handle "429 Too Many Requests" while maintaining Keep-Alive pools? (Implementation: Use Redis-backed rate-limit counters to throttle proactively).
- **Inconsistent State**: What happens if Redis state and PostgreSQL historical data diverge? (Requirement: PostgreSQL is the source of truth for settled trades; Redis is only for active/transient calculation state).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Java microservice MUST expose a gRPC server for receiving strategy commands and state updates from the Python layer.
- **FR-002**: The system MUST implement a Level 2 Order Book engine in Java capable of real-time VWAP (Volume Weighted Average Price) calculations.
- **FR-003**: The Java service MUST maintain a persistent HTTP Keep-Alive connection pool for the Brokerage API to minimize latency on order submission.
- **FR-004**: The system MUST implement a strictly transient Redis schema for storing Kalman filter states, Z-scores, and rate-limit counters.
- **FR-005**: The system MUST implement a robust PostgreSQL schema for historical trade records and telemetry logs, utilizing connection pooling.
- **FR-006**: All execution-related logic (order management, risk checks, stop-loss monitoring) MUST be removed from the Python layer and implemented in the Java service.
- **FR-007**: The system MUST provide a migration script to transition existing historical data from the legacy SQLite database to the new PostgreSQL schema.

### Key Entities *(include if feature involves data)*

- **OrderBook**: Represents the Level 2 bids and asks, used for VWAP calculations.
- **ExecutionSignal**: The gRPC message sent from Python to Java containing trade intent and risk parameters.
- **TransientState**: Redis-stored values (Kalman filter, rate limits) that expire or are overwritten frequently.
- **TradeRecord**: Persistent PostgreSQL entity representing a completed or failed transaction for audit and analysis.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Execution latency (time from Python signal emission to Java order dispatch) MUST be under 10ms in 99% of cases.
- **SC-002**: System MUST handle at least 500 Level 2 order book updates per second with < 1ms VWAP calculation overhead.
- **SC-003**: Brokerage API handshake overhead MUST be reduced by 80% through the use of HTTP Keep-Alive pooling.
- **SC-004**: The migration from SQLite to PostgreSQL MUST result in zero data loss for historical trades.
- **SC-005**: PostgreSQL telemetry logging MUST sustain a burst rate of 1000 records per second without impacting execution performance.

## Assumptions

- **Java Environment**: A high-performance JVM (e.g., GraalVM or OpenJDK 21+) is available for the execution service.
- **Network**: The Python and Java services will run on the same local network or container orchestration platform (Docker/K8s) to minimize gRPC overhead.
- **Brokerage Support**: The brokerage API (e.g., Trading 212) supports persistent HTTP connections and Level 2 data feeds.
- **Schema Compatibility**: The existing SQLite schema can be mapped directly to PostgreSQL with minimal structural changes.
