# Data Model: Strategic Arbitrage Engine

## Entities

### ArbitragePair
Represents two cointegrated assets and their statistical relationship.
- `id`: UUID (Primary Key)
- `ticker_a`: String (e.g., "KO")
- `ticker_b`: String (e.g., "PEP")
- `beta`: Float (Hedge ratio calculated via OLS)
- `status`: Enum (`MONITORING`, `ACTIVE_TRADE`, `PAUSED`)
- `last_z_score`: Float
- `is_cointegrated`: Boolean

### ZScoreHistory
Rolling record of Z-Scores for audit and performance reporting.
- `pair_id`: UUID (Foreign Key)
- `timestamp`: DateTime
- `window`: Integer (30, 60, or 90)
- `value`: Float

### SignalRecord
Logs every triggered signal and its validation status.
- `id`: UUID (Primary Key)
- `pair_id`: UUID (Foreign Key)
- `timestamp`: DateTime
- `z_score`: Float
- `price_a`: Float (Price at signal time)
- `price_b`: Float (Price at signal time)
- `trigger_type`: Enum (`ENTRY`, `EXIT`)
- `ai_validation_status`: Enum (`PENDING`, `GO`, `NO_GO`)
- `ai_rationale`: String
- `user_approval_status`: Enum (`PENDING`, `APPROVED`, `REJECTED`)

### VirtualPieAsset
Local state of portfolio allocations for Trading 212.
- `ticker`: String (Primary Key)
- `target_weight`: Float (Target allocation percentage)
- `current_quantity`: Float (Actually held quantity)
- `currency`: String (Base currency, e.g., "EUR")

### TradeLedger
Auditable record of all trades executed.
- `id`: UUID (Primary Key)
- `timestamp`: DateTime
- `ticker`: String
- `quantity`: Float
- `price`: Float
- `order_type`: Enum (`BUY`, `SELL`)
- `is_paper`: Boolean
- `status`: Enum (`COMPLETED`, `FAILED`)

## Relationships
- **ArbitragePair** has many **ZScoreHistory** records.
- **ArbitragePair** has many **SignalRecord** entries.
- **SignalRecord** triggers one or more **TradeLedger** entries upon approval.
