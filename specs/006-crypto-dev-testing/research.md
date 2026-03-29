# Research: 24/7 Crypto Development Mode

## Decision: Crypto Pairs for Testing
- **Rationale**: Pairs like `BTC-USD` and `ETH-USD` are highly liquid and available 24/7. While they might not be traditionally cointegrated in the same way stocks in the same sector are, they exhibit high correlation which is enough to test the Z-score and agent debate logic.
- **Tickers**: Use `BTC-USD`, `ETH-USD`, `LTC-USD`, `SOL-USD`.

## Decision: Bypassing Operation Hours
- **Rationale**: The `monitor.py` logic currently has a hard check for NYSE/NASDAQ hours. A new environment variable `DEV_MODE=true` will be introduced to bypass this check.
- **Implementation**: Add `if settings.DEV_MODE: return True` to the schedule check.

## Decision: Data Provider for Crypto
- **Rationale**: `yfinance` supports crypto tickers (e.g., `BTC-USD`). Polygon.io also has a crypto endpoint. For simplicity in dev mode, we will prioritize `yfinance` for history and mock/Polygon for real-time.
- **Format**: `yfinance` tickers for crypto follow the `SYMBOL-CURRENCY` format.

## Alternatives Considered
- **Forex**: Operates 24/5, but closes on weekends. Not suitable for full weekend testing.
- **Simulation/Backtest only**: Doesn't validate real-time conetivity or "live" agent responses to changing market conditions.
