# Data Model: Dual-Database Architecture

## 1. Redis Schema (Transient State)

### Kalman Filter State
- **Key**: `kalman:{ticker_pair}`
- **Type**: Hash
- **Fields**:
  - `x`: State vector (serialized JSON)
  - `P`: Covariance matrix (serialized JSON)
  - `K`: Kalman gain (serialized JSON)
  - `last_update`: ISO 8601 timestamp
  - `z_score`: Current computed Z-score (float)

### API Rate Limiters
- **Key**: `ratelimit:{api_name}:{window_start}`
- **Type**: String (Integer)
- **TTL**: 1 hour (configurable)
- **Operations**: `INCR` (Atomic)

### L2 Order Book Snapshot
- **Key**: `l2_snapshot:{ticker}`
- **Type**: Hash
- **Fields**:
  - `vwap`: Float
  - `bid_depth`: Float
  - `ask_depth`: Float
  - `spread`: Float
- **TTL**: 60 seconds (Short-lived)

## 2. PostgreSQL Schema (Persistent State)

### TradeLedger
- `id`: UUID (Primary Key)
- `order_id`: String (Indexed)
- `ticker`: String (Indexed)
- `side`: Enum (BUY/SELL)
- `quantity`: Decimal(20, 10)
- `price`: Decimal(20, 10)
- `fee`: Decimal(20, 10)
- `status`: Enum (PENDING, COMPLETED, FAILED)
- `execution_timestamp`: TIMESTAMP WITH TIME ZONE (Indexed)
- `metadata`: JSONB (For agent reference)

### AgentReasoning
- `id`: UUID (Primary Key)
- `trace_id`: UUID (Indexed)
- `agent_name`: String
- `ticker_pair`: String
- `thought_journal`: TEXT
- `risk_metrics`: JSONB (SHAP/LIME values, Kelly fraction)
- `decision`: Enum (BUY, SELL, HOLD, VETO)
- `created_at`: TIMESTAMP WITH TIME ZONE (Indexed)

### DCASchedules
- `id`: UUID (Primary Key)
- `target_ticker`: String
- `amount`: Decimal(20, 10)
- `frequency`: Enum (DAILY, WEEKLY, MONTHLY)
- `next_execution`: TIMESTAMP WITH TIME ZONE
- `is_active`: Boolean
- `config`: JSONB (Dynamic weights, risk limits)

## 3. SQLite Migration Strategy
1. **Extraction**: Read all rows from legacy SQLite `trades`, `signals`, and `dca` tables.
2. **Transformation**: Map fields to the new PostgreSQL schema (UUIDs, Decimals, JSONB).
3. **Loading**: Use PostgreSQL `COPY` or bulk inserts via SQLAlchemy in a single transaction.
4. **Validation**: Compare row counts and sum of amounts/quantities between source and target.
