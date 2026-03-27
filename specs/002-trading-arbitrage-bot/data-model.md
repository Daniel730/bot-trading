# Data Model: Trading Arbitrage Bot

**Feature**: 002-trading-arbitrage-bot
**Date**: 2026-03-27

## Entities

### `TradingPair`
Represents the relationship between two correlated assets.
- `id`: Unique identifier (string, e.g., "AAPL_MSFT")
- `asset_a`: Ticker of the first asset
- `asset_b`: Ticker of the second asset
- `hedge_ratio`: Calculated coefficient for the spread (float)
- `mean_spread`: 30-90 day average (float)
- `std_spread`: 30-90 day standard deviation (float)
- `last_z_score`: Most recent deviation calculation (float)

### `VirtualPieAsset`
Represents a single asset's target allocation within a logical group.
- `ticker`: The brokerage ticker symbol (PK)
- `target_weight`: Percentage of the pie (float, 0.0 - 1.0)
- `current_quantity`: Number of shares held (float) - **Syncs from API on startup**
- `last_price`: Last fetched market price (float)
- `total_value`: `current_quantity * last_price` (calculated)

### `Signal`
An event triggered when the Z-score exceeds a threshold.
- `id`: Unique identifier (UUID)
- `timestamp`: Time of detection
- `pair_id`: Reference to `TradingPair`
- `z_score`: Value at trigger
- `status`: `PENDING_AI`, `PENDING_USER_CONFIRM`, `APPROVED`, `REJECTED`, `EXECUTED`, `EXPIRED`

### `AuditLogEntry`
A record of the bot's decision-making process.
- `timestamp`: (ISO 8601)
- `signal_id`: Reference to the triggering signal
- `context_summary`: Headlines/news analyzed by Gemini
- `ai_recommendation`: "GO" or "NO-GO"
- `user_confirmation`: "APPROVED" or "REJECTED"
- `ai_rationale`: Brief text from the LLM
- `action_taken`: "BUY", "SELL", "WAIT", "CANCELLED"
- `order_id`: Brokerage reference if executed

## Relationships
- A `TradingPair` consists of two `VirtualPieAsset` entries.
- A `Signal` belongs to one `TradingPair`.
- Each `Signal` results in one or more `AuditLogEntry` records.
