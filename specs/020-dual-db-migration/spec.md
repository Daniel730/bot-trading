# Feature Specification: Dual-Database Migration (Redis & PostgreSQL)

**Feature Branch**: `020-dual-db-migration`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "Update the data model specification to migrate away from SQLite to a dual-database architecture. 1. Redis (Transient State): Define schemas for high-frequency, sub-millisecond data. This MUST include Kalman Filter state matrices, global rate-limit counters, active Z-scores, and short-lived L2 Order Book snapshots. 2. PostgreSQL (Persistent State): Define an ACID-compliant, connection-pooled schema for the Trade Ledger, Agent Reasoning Logs, and DCA Schedules. 3. TSDB Exclusion: Explicitly state that raw high-frequency price tick telemetry MUST NOT be stored in PostgreSQL to prevent index bloat; it will be routed to a Time-Series Database in a future epic."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Real-time Execution Readiness (Priority: P1)

As a high-frequency trading bot, I want my transient state (Kalman filters, Z-scores) to be stored in an in-memory database so that the execution engine can retrieve them with sub-millisecond latency.

**Why this priority**: Core to the performance goals of the new architecture. Without this, the Java execution engine is bottlenecked by disk I/O.

**Independent Test**: Verify that the execution engine can perform 1,000 read/write operations of a Kalman Filter state matrix in under 100ms.

**Acceptance Scenarios**:

1. **Given** a high-frequency market tick, **When** the Kalman filter state is updated in Redis, **Then** the subsequent Z-score calculation MUST retrieve the new state in < 1ms.
2. **Given** a rate-limit check, **When** the global counter is incremented in Redis, **Then** it MUST be atomic across all service instances.

---

### User Story 2 - Financial Integrity & Audit (Priority: P2)

As a fund manager, I want my trade ledger and DCA schedules stored in an ACID-compliant relational database so that I have a durable and consistent record of all financial transactions.

**Why this priority**: Ensures long-term reliability and compliance for the trading bot's operations.

**Independent Test**: Perform a simulated system crash during a bulk trade record insert and verify that the database remains consistent and no partial records exist.

**Acceptance Scenarios**:

1. **Given** a successful trade execution, **When** the trade record is committed to PostgreSQL, **Then** all related balance updates and telemetry logs MUST be part of a single atomic transaction.
2. **Given** a scheduled DCA event, **When** the system retrieves the schedule from PostgreSQL, **Then** it MUST handle connection pooling efficiently under load.

---

### User Story 3 - Long-term System Diagnostics (Priority: P3)

As a developer, I want agent reasoning logs to be searchable and persistent so that I can analyze why a specific trade was or was not executed days or weeks later.

**Why this priority**: Essential for strategy refinement and debugging complex agent interactions.

**Independent Test**: Query the PostgreSQL database for agent logs filtered by ticker and date range, ensuring results are returned within 1 second for a dataset of 100,000 logs.

**Acceptance Scenarios**:

1. **Given** an agent reasoning event, **When** it is logged to PostgreSQL, **Then** it MUST include structured data (JSONB) for flexible querying of reasoning parameters.

---

### Edge Cases

- **Redis Eviction Policy**: What happens if Redis memory limit is reached? (Requirement: Redis MUST be configured with `noeviction` for critical states like Kalman filters; system should alert rather than drop state).
- **PostgreSQL Connection Exhaustion**: How does the system handle a burst of telemetry logs? (Requirement: Use a robust connection pool and ensure telemetry logs do not block trade ledger commits).
- **SQLite Migration Failure**: What happens if the legacy SQLite data cannot be mapped to the new schema? (Requirement: Provide a validation step in the migration script to verify data integrity before final cutover).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST implement a Redis-based schema for transient, high-frequency data, including Kalman Filter state matrices (stored as JSON or binary blobs).
- **FR-002**: The system MUST implement global, atomic rate-limit counters in Redis to manage API quotas across distributed services.
- **FR-003**: Short-lived Level 2 Order Book snapshots (depth/VWAP) MUST be stored in Redis with an explicit TTL (Time-To-Live).
- **FR-004**: The system MUST implement a PostgreSQL-based schema for persistent data, including the Trade Ledger, DCA Schedules, and Agent Reasoning Logs.
- **FR-005**: All PostgreSQL interactions MUST use a managed connection pool to ensure scalability.
- **FR-006**: Agent Reasoning Logs in PostgreSQL MUST support structured JSON data to store complex decision-making context.
- **FR-007**: The system MUST NOT store raw high-frequency price tick telemetry in PostgreSQL; this data MUST be explicitly excluded to prevent index bloat and performance degradation.
- **FR-008**: The system MUST provide a migration tool to transfer existing records from SQLite to the new PostgreSQL schema.

### Key Entities *(include if feature involves data)*

- **KalmanState (Redis)**: Current state of the Kalman filter (transition matrix, covariance matrix, state vector).
- **RateLimitCounter (Redis)**: Atomic integer with TTL representing API usage.
- **TradeRecord (PostgreSQL)**: Durable record of a completed transaction (price, quantity, timestamp, fee).
- **DCASchedule (PostgreSQL)**: Recurring investment configuration (frequency, amount, target).
- **AgentReasoning (PostgreSQL)**: Detailed log of agent decision steps, linked to specific trades or signals.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Redis state retrieval for Kalman filters MUST consistently achieve < 500μs (microseconds) latency.
- **SC-002**: PostgreSQL MUST handle a sustained load of 500 concurrent connection requests via pooling without dropping transactions.
- **SC-003**: The migration script MUST achieve 100% data fidelity when moving records from SQLite to PostgreSQL.
- **SC-004**: PostgreSQL database size growth MUST be reduced by at least 70% by excluding raw price tick telemetry.
- **SC-005**: All trade ledger entries MUST be committed within < 50ms including network and I/O overhead.

## Assumptions

- **Redis Persistence**: Redis is configured for RDB snapshots or AOF persistence to handle service restarts, even for "transient" data.
- **PostgreSQL Version**: Using PostgreSQL 15+ to leverage advanced JSONB indexing and performance optimizations.
- **Network Topology**: Redis and PostgreSQL are hosted in the same VPC/network as the application services to minimize latency.
- **TSDB Future**: A dedicated Time-Series Database (e.g., TimescaleDB, InfluxDB) will be implemented in a future phase for high-frequency price telemetry.
