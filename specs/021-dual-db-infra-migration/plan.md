# Implementation Plan: Dual-Database Infrastructure Migration

**Feature Branch**: `021-dual-db-infra-migration`  
**Status**: Planning  
**Spec**: [spec.md](spec.md)

## Technical Context

- **Current State**: Bot uses a single SQLite database for all data (trades, signals, state).
- **Architecture**: Dual-database split. 
  - **Redis**: For transient, high-frequency mathematical and rate-limit state.
  - **PostgreSQL**: For persistent, transactional records (Trade Ledger, Agent Reasoning).
- **Persistence Strategy**:
  - Redis: AOF with `appendfsync everysec` + named volume.
  - PostgreSQL: Named volume for persistent data directory.

## Constitution Check

- **I. Prioridade à Preservação de Capital**: PostgreSQL ensures ACID compliance for the trade ledger, preventing loss of financial history during system failures.
- **II. Racionalidade Mecânica**: Redis enables sub-millisecond state retrieval for Z-score and Kalman calculations, allowing the engine to react instantly to market data.
- **III. Auditabilidade Total**: PostgreSQL's JSONB support for `AgentReasoning` stores the "Thought Journal" and risk metrics (SHAP/LIME) for full auditability.
- **IV. Operação Estrita**: Database initialization will ensure proper logging of operational hours to ensure the bot respects NYSE/NASDAQ constraints.
- **V. Virtual-Pie First**: PostgreSQL will store the authoritative state of the virtual-pie for cross-session reconciliation.

## Gates

- [x] **Performance Gate**: Redis latency < 1ms for state retrieval.
- [x] **Durability Gate**: PostgreSQL ACID transactions for trade ledger.
- [x] **Capacity Gate**: Telemetry exclusion to prevent index bloat.

## Phase 0: Research & Discovery
- **Status**: Completed
- **Artifact**: [research.md](research.md)
- **Key Decisions**: Use `redis:7-alpine`, `postgres:15-alpine`, `redis-py`, and `SQLAlchemy` with `asyncpg`.

## Phase 1: Design & Infrastructure
- **Status**: Completed
- **Artifacts**: 
  - [data-model.md](data-model.md)
  - [quickstart.md](quickstart.md)
- **Actions**:
  - Defined Redis Hash structures for Kalman filters.
  - Defined PostgreSQL table schemas for trade ledger and agent reasoning.
  - Planned fresh initialization scripts to replace legacy SQLite data.

## Phase 2: Implementation (Task List)
- **P0: Infrastructure Updates**:
  - Update `docker-compose.yml` to include Redis and PostgreSQL services.
  - Configure Redis AOF and PostgreSQL named volumes.
  - Create `scripts/init_db.py` for new schema initialization.
- **P1: Data Layer Refactor**:
  - Implement `RedisService` for transient state management.
  - Implement `PersistenceService` (PostgreSQL) using SQLAlchemy and asyncpg.
  - Remove all legacy SQLite interaction logic.
- **P2: Service Integration**:
  - Update `ArbitrageService` to use Redis for Kalman state updates and Z-score calculations.
  - Update `RiskService` to store Reasoning Logs in PostgreSQL.
  - Integrate global rate limiters in Redis for brokerage API calls.

## Re-evaluation of Constitution Check
The design reinforces all constitutional principles by providing the technical infrastructure required for sub-millisecond "Mechanical Rationality" and durable "Total Auditability."
