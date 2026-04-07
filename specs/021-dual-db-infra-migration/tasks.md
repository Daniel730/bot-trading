# Tasks: Dual-Database Infrastructure Migration

**Input**: Design documents from `/specs/021-dual-db-infra-migration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Tests are included to verify persistence and recovery as per success criteria.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and environment configuration

- [x] T001 Update `.env.template` with Redis and PostgreSQL connection variables
- [x] T002 Update `requirements.txt` with `redis`, `sqlalchemy`, and `asyncpg`
- [x] T003 [P] Create `src/config.py` updates to validate new database environment variables

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

- [x] T004 [P] Update `docker-compose.yml` to include `redis:7-alpine` and `postgres:15-alpine` services
- [x] T005 [P] Configure Redis AOF persistence and named volumes (`redis_data`, `postgres_data`) in `docker-compose.yml`
- [x] T006 Implement `PersistenceService` using SQLAlchemy 2.0 and `asyncpg` in `src/services/persistence_service.py`
- [x] T007 Implement `RedisService` using `redis.asyncio` in `src/services/redis_service.py`
- [x] T008 Create database initialization script `scripts/init_db.py` for PostgreSQL schema creation
- [x] T009 [P] Remove all legacy `sqlite3` imports and logic from the codebase (check `src/services/`, `src/agents/`, `src/utils.py`)

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 3 - Infrastructure Reliability (Priority: P3) 🎯 Foundation

**Goal**: Provision a standard, containerized environment for both databases.

**Independent Test**: Run `docker-compose up -d` and verify both databases are healthy and accessible.

### Implementation for User Story 3

- [x] T010 [P] [US3] Implement health checks for Redis and PostgreSQL in `docker-compose.yml`
- [x] T011 [US3] Verify connection pooling configuration (pool_size=20) in `src/services/persistence_service.py`
- [x] T012 [US3] Add validation in `PersistenceService` to exclude raw price tick telemetry from PostgreSQL storage

---

## Phase 4: User Story 1 - Recovery of Execution State (Priority: P1) 🎯 MVP

**Goal**: Recover Kalman filter states from Redis after a restart to prevent "amnesia".

**Independent Test**: Update a Kalman state, restart the Redis container, and verify the state is recovered by `ArbitrageService`.

### Tests for User Story 1

- [ ] T013 [P] [US1] Create integration test `tests/integration/test_kalman_recovery.py` to verify warm start from Redis

### Implementation for User Story 1

- [x] T014 [US1] Implement `save_kalman_state` and `get_kalman_state` in `src/services/redis_service.py`
- [x] T015 [US1] Update `ArbitrageService.initialize_pair()` in `src/services/arbitrage_service.py` to attempt a warm start from Redis
- [x] T016 [US1] Update `on_market_tick` in `src/services/arbitrage_service.py` to asynchronously save Kalman state to Redis after each update
- [x] T017 [US1] Implement global rate-limit counters in `src/services/redis_service.py` using atomic `INCR`

---

## Phase 5: User Story 2 - Permanent Trade History (Priority: P2)

**Goal**: Permanently store trade ledger and agent reasoning logs in PostgreSQL.

**Independent Test**: Execute a trade, delete the PostgreSQL container, recreate it, and verify the trade record persists.

### Tests for User Story 2

- [ ] T018 [P] [US2] Create integration test `tests/integration/test_trade_persistence.py` to verify PostgreSQL volume durability

### Implementation for User Story 2

- [x] T019 [P] [US2] Define `TradeLedger` and `AgentReasoning` models in `src/models/` using SQLAlchemy
- [x] T020 [US2] Update `RiskService.evaluate_signal()` in `src/services/risk_service.py` to store reasoning logs in PostgreSQL
- [x] T021 [US2] Update `DcaService` in `src/services/dca_service.py` to use PostgreSQL for schedules and history
- [x] T022 [US2] Link `TradeLedger` entries to `AgentReasoning` logs via `trace_id` for full auditability

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final integration and validation

- [x] T023 [P] Ensure all database connections are initialized in `src/main.py` using `asyncio.gather`
- [x] T024 [P] Implement graceful shutdown logic in `src/main.py` to close all database pools
- [x] T025 Update `README.md` and `docs/` with the new dual-database architecture details
- [x] T026 Run `scripts/verify_sc.py` to confirm all success criteria are met
