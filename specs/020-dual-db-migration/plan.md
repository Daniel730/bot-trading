# Implementation Plan: Dual-Database Migration (Redis & PostgreSQL)

**Feature Branch**: `020-dual-db-migration`  
**Status**: Planning  
**Spec**: [spec.md](spec.md)

## Technical Context

- **Current State**: Bot uses SQLite for all data (trades, signals, state).
- **Architecture**: Dual-database split. 
  - **Redis**: Transient, high-frequency mathematical and rate-limit state.
  - **PostgreSQL**: Persistent, transactional records (Trade Ledger, Agent Reasoning).
- **TSDB Strategy**: High-frequency price tick telemetry is EXCLUDED from PostgreSQL.

## Constitution Check

- **I. Prioridade à Preservação de Capital**: PostgreSQL ensures ACID compliance for the trade ledger, preventing loss of financial history during system failures.
- **II. Racionalidade Mecânica**: Redis enables sub-millisecond state retrieval for Z-score and Kalman calculations, allowing the engine to react instantly to market data.
- **III. Auditabilidade Total**: PostgreSQL's JSONB support for `AgentReasoning` stores the "Thought Journal" and risk metrics (SHAP/LIME) for full auditability.
- **IV. Operação Estrita**: Database migration includes logging for operational hours to ensure the bot respects NYSE/NASDAQ constraints.
- **V. Virtual-Pie First**: PostgreSQL stores the authoritative state of the virtual-pie for cross-session reconciliation.

## Gates

- [x] **Performance Gate**: Redis latency < 1ms for state retrieval.
- [x] **Durability Gate**: PostgreSQL ACID transactions for trade ledger.
- [x] **Capacity Gate**: Telemetry exclusion to prevent index bloat.

## Phase 0: Research & Discovery
- **Status**: Completed
- **Artifact**: [research.md](research.md)
- **Key Decisions**: Use `redis-py`, `SQLAlchemy` with `asyncpg`, and JSONB for reasoning logs.

## Phase 1: Design & Infrastructure
- **Status**: Completed
- **Artifacts**: 
  - [data-model.md](data-model.md)
  - [quickstart.md](quickstart.md)
- **Actions**:
  - Defined Redis Hash structures for Kalman filters.
  - Defined PostgreSQL table schemas with relational integrity.
  - Drafted migration strategy for legacy SQLite data.

## Phase 2: Implementation (Task List)
- **P0: Infrastructure Updates**:
  - Update `docker-compose.yml` to include Redis and PostgreSQL.
  - Create `scripts/init_db.py` for schema initialization.
- **P1: Data Layer Refactor**:
  - Implement `RedisService` for transient state.
  - Implement `PersistenceService` (PostgreSQL) for transactional data.
  - Create the SQLite-to-PostgreSQL migration script.
- **P2: Service Integration**:
  - Update `ArbitrageService` to use Redis for Kalman updates.
  - Update `RiskService` to store Reasoning Logs in PostgreSQL.
  - Update `DcaService` to use PostgreSQL for schedules.

## Re-evaluation of Constitution Check
The design reinforces all constitutional principles by providing the technical infrastructure required for sub-millisecond "Mechanical Rationality" and durable "Total Auditability."
