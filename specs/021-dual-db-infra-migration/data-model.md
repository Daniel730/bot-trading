# Data Model: Dual-Database Infrastructure

## 1. Redis (Transient State)
- **Key Strategy**: Use prefixed keys for isolation (e.g., `kalman:{pair}`, `ratelimit:{api}`).
- **Kalman State**: Stored as a Hash for fast retrieval and update.
  - Fields: `x` (vector), `P` (matrix), `last_tick`.
- **Rate Limiters**: Stored as Integers with atomic `INCR` and `EXPIRE`.

## 2. PostgreSQL (Persistent Records)
- **Trade Ledger**:
  - `id`: UUID (Primary Key)
  - `timestamp`: TIMESTAMP WITH TIME ZONE
  - `ticker`: VARCHAR(20)
  - `side`: VARCHAR(10)
  - `quantity`: DECIMAL(20, 10)
  - `price`: DECIMAL(20, 10)
  - `fee`: DECIMAL(20, 10)
  - `status`: VARCHAR(20)
- **Agent Reasoning Logs**:
  - `id`: UUID (Primary Key)
  - `timestamp`: TIMESTAMP WITH TIME ZONE
  - `agent_id`: VARCHAR(50)
  - `ticker`: VARCHAR(20)
  - `thought_journal`: TEXT
  - `risk_metrics`: JSONB (SHAP values, Kelly fraction)
  - `action`: VARCHAR(20)

## 3. Data Relationships
- Trade Ledger entries should link to their corresponding Agent Reasoning log via a `trace_id` for full auditability.

## 4. Initialization
- Redis: No schema required, but initialization script will pre-warm rate limiters if necessary.
- PostgreSQL: Initialization script will use SQLAlchemy `create_all()` or raw SQL for table creation and indexing.
