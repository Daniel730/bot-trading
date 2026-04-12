# Data Model: Dynamic Risk and Volatility Switch

**Feature Branch**: `028-dynamic-risk-and-volatility-switch`  
**Created**: 2026-04-06  
**Status**: Draft  
**Plan**: [specs/028-dynamic-risk-and-volatility-switch/plan.md]

## PostgreSQL Schema Updates

### Table: `portfolio_performance`

Tracks the historical performance metrics used to scale risk.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary Key. |
| `timestamp` | TIMESTAMP | Time of capture (Daily/Hourly). |
| `total_equity` | DECIMAL(18,10) | Current account balance + positions. |
| `rolling_sharpe_30d` | DECIMAL(10,4) | Sharpe ratio over the last 30 days. |
| `max_drawdown_pct` | DECIMAL(10,4) | Peak-to-trough decline since inception. |
| `current_risk_multiplier` | DECIMAL(10,4) | The final calculated `RiskScale`. |

## Redis Schema Updates

### Key: `volatility:entropy:L2`

Stores the real-time entropy calculation for the L2 book.

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | STRING | The asset ticker (e.g., BTC-USD). |
| `entropy_value` | FLOAT | Shannon Entropy calculation. |
| `status` | ENUM | NORMAL, HIGH_VOLATILITY, TOXIC. |
| `updated_at` | TIMESTAMP | Last update time. |

## gRPC Metadata

No changes to the `.proto` are required as `max_slippage_pct` already exists in `ExecutionRequest`. However, the *usage* of this field becomes dynamic.

| Message | Field | Dynamic Source |
|---------|-------|----------------|
| `ExecutionRequest` | `max_slippage_pct` | `VolatilitySwitchService.get_optimal_slippage()` |
| `ExecutionResponse` | `message` | Includes "Volatility Switch Veto" if rejected. |
