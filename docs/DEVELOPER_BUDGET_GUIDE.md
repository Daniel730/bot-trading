# 🛠️ Developer Guide: Unified Budget Management

This document explains the unified budgeting system introduced to manage capital allocation across multiple trading venues (Trading 212 and Web3/Crypto).

## 1. Overview

The `BudgetService` provides a persistent, cross-session mechanism to enforce capital caps for different venues. It decouples the "Where to trade" (Venue) from the "How much to trade" (Budget).

### Key Components:
- **`src/services/budget_service.py`**: The core service managing budget state.
- **SQLite (`system_state` table)**: Persists the `budget_used_{VENUE}` values.
- **`src/config.py`**: Defines the caps via `T212_BUDGET_USD` and `WEB3_BUDGET_USD`.

## 2. Venue Determination

Venues are determined centrally in `BrokerageService.get_venue(ticker)`. 
- **T212**: Standard equity tickers.
- **WEB3**: Tickers ending in `-USD` (Crypto spot).

Developers should **never** hardcode `"-USD" in ticker` checks in the monitor or other services. Always use:
```python
venue = brokerage_service.get_venue(ticker)
```

## 3. The Budget Lifecycle

### A. Sizing (The Monitor)
Before executing a trade, the `ArbitrageMonitor` queries the budget service to determine the "Effective Cash".

```python
actual_available = brokerage_cash - pending_orders_value
effective_cash = budget_service.get_effective_cash(venue, actual_available)
```
`effective_cash` is the minimum of:
1. The real money in the account/wallet.
2. The remaining allocated budget (`Cap - Used`).

### B. Execution (Brokerage Service)
When `place_value_order` is called, the `BrokerageService` routes the order to the correct provider. Upon success, it updates the used budget:

```python
if result.get("status") != "error":
    budget_service.update_used_budget(venue, amount)
```

## 4. Database Schema

Budgets are stored in the `system_state` table:
- `budget_used_T212`: Total USD spent on T212 since last reset.
- `budget_used_WEB3`: Total USD spent on Web3 since last reset.

## 5. Adding a New Venue

To add a third venue (e.g., "BINANCE"):
1. Add `BINANCE_BUDGET_USD` to `src/config.py`.
2. Update `BudgetService._init_budgets` to include `budget_used_BINANCE`.
3. Update `BrokerageService.get_venue` logic to resolve appropriate tickers to `"BINANCE"`.
4. The monitor and execution logic will automatically pick up the new venue's budget cap.

## 6. Maintenance Commands

To reset budgets (e.g., daily), use the `BudgetService.reset_budget(venue)` method. This can be integrated into a daily maintenance daemon if needed.
