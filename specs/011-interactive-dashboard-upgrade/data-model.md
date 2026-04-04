# Data Model: Interactive Dashboard Upgrade

## Dashboard State (Internal)
The `DashboardState` singleton will be expanded to include:

- `portfolio_metrics`: 
    - `total_invested`: float (current exposure)
    - `total_revenue`: float (realized PnL)
    - `daily_profit`: float (current day realized PnL)
    - `active_trades_count`: int
- `active_signals`: list of dicts:
    - `ticker_a`: str
    - `ticker_b`: str
    - `z_score`: float
    - `status`: str (Analyzing, Signal Detected, Executing)
- `system_status`:
    - `uptime`: str
    - `mode`: str (Live / Shadow / Dev)

## SQLite Queries for Dashboard
To populate the metrics, the following queries will be used via `PersistenceManager`:

- **Revenue**: `SELECT SUM(total_pnl) FROM trade_records WHERE status = 'Closed' AND is_shadow = 1`
- **Current Investment**: `SELECT SUM(size_a * entry_price_a + size_b * entry_price_b) FROM trade_records WHERE status = 'Open' AND is_shadow = 1`
- **Daily Profit**: `SELECT SUM(total_pnl) FROM trade_records WHERE status = 'Closed' AND entry_timestamp >= date('now') AND is_shadow = 1`
- **Available Cash**: External call to `BrokerageService.get_account_cash()` (Live) or `PersistenceManager` balance (Shadow).

## UI Components
- **Header**: System health, uptime, and mode.
- **Metrics Panel**: High-level financial cards (Revenue, Investments).
- **Trading Feed**: List of active pairs and their Z-scores (with Possible Buy/Sell markers).
- **Thought Journal**: Interactive scroll of recent bot decisions.
- **Robot Interface**: Animations tied to bot actions (Mood: Idle, Analyzing, Executing).
