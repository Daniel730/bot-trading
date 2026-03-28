# Data Model: Strategic Arbitrage Engine

## Entities

### ArbitragePair
- **ID**: UUID (Primary Key)
- **TickerA**: String (e.g., "KO")
- **TickerB**: String (e.g., "PEP")
- **Beta**: Float (Cointegration coefficient)
- **Status**: Enum (MONITORING, ACTIVE_TRADE, PAUSED)
- **LastZScore**: Float
- **IsCointegrated**: Boolean (ADF test result)

### ZScoreHistory
- **PairID**: UUID (Foreign Key)
- **Timestamp**: DateTime
- **Window**: Integer (30, 60, or 90)
- **Value**: Float

### SignalRecord
- **ID**: UUID (Primary Key)
- **PairID**: UUID (Foreign Key)
- **Timestamp**: DateTime
- **ZScore**: Float
- **TriggerType**: Enum (ENTRY, EXIT)
- **AIValidationStatus**: Enum (PENDING, GO, NO_GO)
- **AIRationale**: String
- **UserApprovalStatus**: Enum (PENDING, APPROVED, REJECTED)

### VirtualPieAsset
- **Ticker**: String (Primary Key)
- **TargetWeight**: Float (0.0 to 1.0)
- **CurrentQuantity**: Float
- **Currency**: String (Account base currency)

### TradeLedger
- **ID**: UUID (Primary Key)
- **Timestamp**: DateTime
- **Ticker**: String
- **Quantity**: Float
- **Price**: Float
- **OrderType**: Enum (BUY, SELL)
- **IsPaper**: Boolean (Paper vs Live)
- **Status**: Enum (COMPLETED, FAILED)
