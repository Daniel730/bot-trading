# Developer Guide: Venue Budgets

`BudgetService` enforces optional spend caps for the active execution venue. It exists so the strategy can make sizing decisions without hardcoding capital rules throughout the monitor.

## Current Venues

| Venue | Routed By | Budget setting | State key |
|---|---|---|---|
| `ALPACA` | active brokerage route when `BROKERAGE_PROVIDER=ALPACA` | `ALPACA_BUDGET_USD` | `budget_used_ALPACA` |

Trading 212 and Web3 routes are legacy/disabled in the current runtime. `BROKERAGE_PROVIDER` values other than `ALPACA` fail startup.

Venue resolution is centralized in `BrokerageService.get_venue(ticker)`. Do not duplicate provider assumptions in callers.

## Storage

Budget usage is stored in SQLite through `PersistenceManager` system state:

```text
budget_used_ALPACA
```

The Alpaca value is initialized once and is not reset on restart. This lets the bot keep respecting spend caps across process restarts where a cap exists.

## Sizing Flow

Before execution, the monitor asks the brokerage service for available cash and pending-order value, then applies the venue budget:

```python
actual_available = brokerage_cash - pending_orders_value
effective_cash = budget_service.get_effective_cash(venue, actual_available)
```

If the configured venue budget is `0`, the cap is disabled and `actual_available` is returned.

If the configured venue budget is positive:

```text
effective_cash = min(actual_available, budget_cap - used_budget)
```

## Spend Updates

`BrokerageService.place_value_order()` adds to the used budget when:

- the broker result is explicitly `status=filled`;
- the result is not marked `requires_reconciliation`;
- `PAPER_TRADING=false`.

Paper trading does not consume live venue budget.

## Dashboard Metrics

The dashboard polls budget information and displays per-venue metrics:

- available cash;
- pending orders;
- spendable cash;
- configured daily/venue budget;
- used budget;
- usage percent;
- venue P&L/investment snapshots.

## Resetting A Budget

Use the service method:

```python
budget_service.reset_budget("ALPACA")
```

This is intentionally not automatic. If daily reset behavior is desired, wire it through a scheduled maintenance job with an explicit audit event.

## Adding A Venue

1. Add a config field such as `BINANCE_BUDGET_USD` to `Settings`.
2. Initialize `budget_used_BINANCE` in `BudgetService._init_budgets()`.
3. Extend `BrokerageService.get_venue()` to return `BINANCE` for the relevant tickers.
4. Add the execution path in `place_value_order()`.
5. Add dashboard metrics if the venue should be visible to operators.
6. Add unit tests for venue routing, budget caps, and update/reset behavior.
