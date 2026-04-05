# Research: Dual-Database Migration (Redis & PostgreSQL)

## Decision: Redis for High-Frequency State
- **Implementation**: Use `redis-py` with `hset`/`hget` for Kalman filter matrices to keep related state components together.
- **Rationale**: Sub-millisecond latency is mandatory for the execution loop. Redis provides atomic operations required for rate-limiting and shared state across potential multiple service instances.
- **Alternatives Considered**: 
  - **In-memory Python dicts**: Faster but not shareable across processes and lost on crash.
  - **SQLite `:memory:`**: Slower than Redis and harder to manage for structured matrix data.

## Decision: PostgreSQL for Persistent Records
- **Implementation**: Use `SQLAlchemy` with `asyncpg` and `autocommit=False` to ensure transaction integrity. Connection pooling via `QueuePool` (default in SQLAlchemy).
- **Rationale**: ACID compliance is non-negotiable for the Trade Ledger. JSONB support in PostgreSQL is ideal for storing unstructured Agent Reasoning logs while maintaining queryability.
- **Alternatives Considered**: 
  - **SQLite**: Current solution, but lacks robust concurrent write support and advanced indexing for large telemetry datasets.
  - **MongoDB**: Good for logs, but lacks the relational integrity required for financial ledgers.

## Decision: Schema Design for Kalman Matrices
- **Implementation**: Store Kalman matrices as serialized JSON strings or MessagePack blobs in Redis Hashes.
- **Rationale**: Matrices ($x, P, K, Q, R$) are updated as a unit. Storing them in a Hash allows fetching the entire filter state in one `HGETALL` call.

## Decision: Rate-Limiting Strategy
- **Implementation**: Use Redis `INCR` with `EXPIRE`.
- **Rationale**: Simple, atomic, and automatically handles window resetting.

## Decision: Connection Pooling Configuration
- **Implementation**: Set `pool_size=20`, `max_overflow=10`, and `pool_timeout=30`.
- **Rationale**: Based on success criteria of handling 500 concurrent requests (mostly read-heavy agents) and 50ms commit targets for the ledger.

## Decision: TSDB Exclusion Enforcement
- **Implementation**: Validation layer in the Telemetry service that throws an error if high-frequency tick data is passed to the PostgreSQL router.
- **Rationale**: Prevents accidental index bloat as per FR-007.
