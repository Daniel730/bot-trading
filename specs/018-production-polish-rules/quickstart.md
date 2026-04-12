# Quickstart: Production-Grade Polish & Reliability Enforcement

## Prerequisites

- **Python 3.11+**
- **pytz** and **zoneinfo** libraries.
- **SQLite** or **Redis** for state persistence.

## Configuration Changes

Update your `.env` or `config.py` to use New York market hours:

```env
# New York Market Hours (ET)
START_HOUR=9
START_MINUTE=30
END_HOUR=16
END_MINUTE=0
```

## How it works

### 1. State Persistence
The bot now automatically saves the state of its Kalman Filter mathematical models (Hedge Ratio, Intercept, Covariance) after every update. This ensures that if the service restarts, it can resume trading immediately without having to "warm up" its models from historical data.

### 2. API Caching
Requests to the Trading 212 API for portfolio data or order status are now cached for **5 seconds**. This significantly reduces the risk of being rate-limited (429 errors) when multiple components (Dashboard, Analysts, Orchestrator) request data simultaneously.

### 3. Slippage Guards (1%)
Market orders are now automatically converted to limit orders with a **1% slippage buffer**. 
- **Buy orders**: `limitPrice = current_price * 1.01`
- **Sell orders**: `limitPrice = current_price * 0.99`

This protects you from paying significantly more than the quoted price during high volatility.

### 4. Dividend Reinvestment (DRIP) Safety
The bot now checks your available free cash before attempting to reinvest a dividend. It will only execute a trade if it can cover the cost using either the dividend amount or your available cash, preventing overdraft errors.

### 5. Timezone Sync
The bot now explicitly tracks **'America/New_York'** time for market operations. It stays synchronized with the NYSE/NASDAQ regardless of server location or Daylight Saving Time (DST) changes.
