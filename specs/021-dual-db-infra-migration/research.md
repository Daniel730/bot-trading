# Research: Dual-Database Infrastructure Migration

## Decision: Redis Configuration for Performance and Persistence
- **Decision**: Use `redis:7-alpine` with AOF persistence.
- **Rationale**: AOF with `appendfsync everysec` provides a balance between high-frequency write performance and data durability (maximum 1 second of data loss in case of crash). The Alpine image keeps the infrastructure footprint small.
- **Alternatives Considered**: RDB (too infrequent for high-frequency Kalman updates), fsync always (too slow for the execution loop).

## Decision: PostgreSQL Configuration for Durability
- **Decision**: Use `postgres:15-alpine` with Docker named volumes.
- **Rationale**: PostgreSQL 15 provides robust JSONB support for reasoning logs and reliable ACID transactions for the trade ledger. Named volumes ensure data survives container updates and restarts.

## Decision: Database Client Libraries for Python
- **Decision**: Use `redis-py` for Redis and `SQLAlchemy` with `asyncpg` for PostgreSQL.
- **Rationale**: `asyncpg` is the fastest asynchronous driver for PostgreSQL, fitting the bot's async requirements. `redis-py` has excellent async support.

## Decision: Docker Compose Structure
- **Decision**: Separate database services with dedicated health checks.
- **Rationale**: Ensures the bot service only starts when both databases are ready to accept connections.
- **Best Practices**: Use environment variables for all credentials and connection strings.
