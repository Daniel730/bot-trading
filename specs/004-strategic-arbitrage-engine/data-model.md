# Data Model: Strategic Arbitrage Engine

## Entities

### ArbitragePair
Represents a cointegrated pair of assets monitored by the system.
- `id`: UUID (Primary Key)
- `ticker_a`: String (e.g., "KO")
- `ticker_b`: String (e.g., "PEP")
- `beta`: Float (Hedge ratio calculated via OLS)
- `status`: Enum (`MONITORING`, `ACTIVE_TRADE`, `PAUSED`)
- `last_z_score`: Float
- `is_cointegrated`: Boolean

### SignalRecord
Logs generated signals and their validation history.
- `id`: UUID (Primary Key)
- `pair_id`: UUID (Foreign Key)
- `timestamp`: DateTime
- `z_score`: Float
- `price_a`: Float
- `price_b`: Float
- `trigger_type`: Enum (`ENTRY`, `EXIT`)
- `ai_validation_status`: Enum (`PENDING`, `GO`, `NO_GO`)
- `ai_rationale`: String
- `user_approval_status`: Enum (`PENDING`, `APPROVED`, `REJECTED`)

### VirtualPieAsset
Local state of the "Virtual Pie" allocations.
- `ticker`: String (Primary Key)
- `target_weight`: Float
- `current_quantity`: Float
- `currency`: String

### TradeLedger
Audit log of all executed trades (Live or Paper).
- `id`: UUID (Primary Key)
- `timestamp`: DateTime
- `ticker`: String
- `quantity`: Float
- `price`: Float
- `order_type`: Enum (`BUY`, `SELL`)
- `is_paper`: Boolean
- `status`: Enum (`COMPLETED`, `FAILED`)

## Relationships
- **ArbitragePair** 1:N **SignalRecord**
- **SignalRecord** 1:N **TradeLedger** (One signal results in two orders for the pair)
