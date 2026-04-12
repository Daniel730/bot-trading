# Feature Specification: Dual-Database Infrastructure Migration

**Feature Branch**: `021-dual-db-infra-migration`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "Update the data model and infrastructure specification for the dual-database architecture. 1. Redis: Configure `redis:7-alpine` with an AOF persistence model (`appendonly yes`, `appendfsync everysec`). Map `/data` to a `redis_data` named volume. This handles transient state (Kalman matrices, rate limits). 2. PostgreSQL: Configure a persistent, ACID-compliant setup mapped to a `postgres_data` named volume for the Trade Ledger and Agent Logs. 3. Migration: Drop the existing SQLite database entirely and use fresh initialization scripts."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recovery of Execution State (Priority: P1)

As a trading bot, I want my mathematical states (Kalman filters) to be recovered immediately after a container restart so that I can resume trading without "amnesia" or losing calculated alpha.

**Why this priority**: Crucial for operational continuity and risk management. Cold-starting Kalman filters can lead to incorrect signals and financial losses.

**Independent Test**: Simulate a container restart. Verify that the Kalman filter state in Redis matches the pre-restart state within 1 second.

**Acceptance Scenarios**:

1. **Given** a running bot with updated Kalman state in Redis, **When** the Redis container is restarted, **Then** the bot MUST be able to read the exact same state from the `redis_data` volume.

---

### User Story 2 - Permanent Trade History (Priority: P2)

As a fund manager, I want all trade ledger entries to be permanently stored so that I have a complete and immutable audit trail that survives infrastructure updates.

**Why this priority**: Essential for regulatory compliance, performance analysis, and tax reporting.

**Independent Test**: Delete the PostgreSQL container and recreate it using Docker Compose. Verify that the trade ledger data is intact.

**Acceptance Scenarios**:

1. **Given** existing trade records in PostgreSQL, **When** the database container is destroyed and recreated, **Then** the records MUST still be available in the `postgres_data` volume.

---

### User Story 3 - Infrastructure Reliability (Priority: P3)

As a developer, I want a standard, containerized environment for both databases so that deployment is predictable and the bot's data layer is isolated from host system changes.

**Why this priority**: Simplifies environment setup and reduces "it works on my machine" issues.

**Independent Test**: Provision a fresh environment using Docker Compose and verify that both databases are initialized correctly using the new scripts.

**Acceptance Scenarios**:

1. **Given** a new environment, **When** Docker Compose is started, **Then** Redis and PostgreSQL containers MUST be healthy and initialized with the required schemas.

---

### Edge Cases

- **Redis Volume Corruption**: How does the system handle a corrupted AOF file? (Standard behavior: Redis will fail to start; manual repair or fresh state from strategy layer is required).
- **PostgreSQL Connection Pool Exhaustion**: How does the bot handle heavy log bursts? (Standard behavior: Bot waits for connection; retry logic required).
- **Simultaneous Database Failure**: How does the bot react if both Redis and PostgreSQL are unavailable? (Requirement: Bot MUST enter a safe/standby mode and stop execution).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST employ `redis:7-alpine` for transient state management.
- **FR-002**: Redis MUST be configured with Append Only File (AOF) persistence using `appendonly yes` and `appendfsync everysec`.
- **FR-003**: Redis `/data` directory MUST be mapped to a Docker named volume called `redis_data`.
- **FR-004**: System MUST employ PostgreSQL for persistent record management (Trade Ledger, Agent Logs).
- **FR-005**: PostgreSQL data directory MUST be mapped to a Docker named volume called `postgres_data`.
- **FR-006**: System MUST provide fresh initialization scripts to create the required database schemas for both Redis and PostgreSQL.
- **FR-007**: The existing SQLite database usage MUST be removed from the bot's codebase.

### Key Entities *(include if feature involves data)*

- **TransientState**: In-memory representation of mathematical models (matrices, vectors) and rate-limit counters stored in Redis.
- **PersistentRecord**: Relational data representing financial transactions, agent reasoning steps, and audit logs stored in PostgreSQL.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of mathematical state is recovered from Redis within 1 second of bot service re-connection after a restart.
- **SC-002**: Zero data loss for trade ledger entries across container destruction and reconstruction cycles.
- **SC-003**: Bot initialization time on a fresh system (excluding image download) is under 2 minutes.
- **SC-004**: System handles up to 500 concurrent I/O operations per second across both databases without performance degradation of the core execution loop.

## Assumptions

- **Fresh Start**: Historical data from the SQLite database does not require automated migration and will be handled as a fresh start.
- **Docker Environment**: The system is deployed in an environment where Docker and Docker Compose are available.
- **Network Performance**: The bot and database containers will communicate over a shared Docker network for optimal performance.
