# Contract: Brokerage & Execution Tools (FastMCP)

## Purpose
Standardized tool definitions exposed via FastMCP to the LangGraph `Decision Core`. These tools encapsulate implementation details (APIs, Math) into deterministic functions.

## Tool Definitions

### `get_market_data`
Fetches real-time or historical data for one or more tickers.
- **Arguments**:
  - `tickers` (list[string]): List of symbols (e.g., ['KO', 'PEP']).
  - `source` (string): 'Polygon-WS', 'yfinance'.
  - `lookback` (string): Time window for baseline (e.g., '30d', '1h').
- **Response**: JSON with OHLCV data and calculated Z-score if applicable.

### `execute_trade`
Sends execution commands to the Trading 212 wrapper.
- **Arguments**:
  - `ticker` (string): Symbol to trade.
  - `side` (string): 'BUY' or 'SELL'.
  - `quantity` (float): Number of shares (fractional supported).
  - `mode` (string): 'LIVE' or 'SHADOW'.
- **Response**: `TradeRecord` summary (success/failure, execution price).

### `calculate_risk_metrics`
Computes position sizing and tail risk.
- **Arguments**:
  - `portfolio` (list[dict]): Current Virtual Pie state.
  - `confidence_score` (float): 0.0 to 1.0 (from Agent debate).
  - `method` (string): 'Monte-Carlo-VaR', 'Kelly-Fractional'.
- **Response**: `suggested_size` (float), `var_95` (float).

### `post_to_thought_journal`
Persists AI reasoning for audit compliance.
- **Arguments**:
  - `signal_id` (UUID)
  - `agent_logs` (dict): Bull, Bear, and News analyst outputs.
  - `decision_factors` (dict): Feature importance (SHAP/LIME).
- **Response**: `journal_id` (UUID).

### `send_interactive_notification`
Handles Telegram human-in-the-loop approvals.
- **Arguments**:
  - `message` (string): Trade summary.
  - `buttons` (list[string]): Action labels (e.g., ['Approve', 'Reject']).
- **Response**: User selection (after block/await).

### `generate_performance_tearsheet`
Triggers QuantStats report generation.
- **Arguments**:
  - `start_date` / `end_date` (string)
  - `benchmark` (string): Default 'SPY'.
- **Response**: URL/Path to HTML report.
