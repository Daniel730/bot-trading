1. Execution & Brokerage Resilience
Idempotency & Duplicate Execution: The BrokerageService must implement Idempotency Keys (UUIDs) appended as client_order_id to every order payload to prevent duplicate executions during network dropouts. If a timeout occurs, the system must query the broker's endpoint by that UUID before retrying.

State Desync from Partial Fills: The bot must track open positions based on explicit Order Execution Reports (using WebSockets or polling for confirmations) instead of relying solely on the requested order quantities.

Tick Size Violations: The system must fetch tick_size metadata for assets and use decimal.Decimal to round limit prices exactly to the allowed increments to avoid broker rejections.

API Caching: Implement a 5-second Time-To-Live (TTL) cache for /portfolio and /orders endpoints to prevent 429 Rate Limit API bans. This cache should use a "Single-Flight" pattern or lock to prevent the "Thundering Herd" problem on high-frequency dashboard reloads.

Price Fallbacks & Retries: The data_service must implement a maximum of 3 retry attempts with exponential backoff (1s, 2s, 4s) for price fallbacks. If both the primary broker and the data service return 0.0, the calculation must immediately fail and the order must be rejected.

2. Quantitative & Mathematical Fixes
Kalman Filter Covariance Guard: Implement a covariance guard to check for NaN and Inf values before updating states; if detected, reset the filter or apply a ridge regression penalty to prevent math explosions.

Mathematical Intercept: The Statistical Arbitrage OLS regression must explicitly use statsmodels.api.add_constant() to establish the mathematical intercept.

Corporate Actions (Splits/Dividends): Ensure adjusted=True is enforced on all historical data queries. A daily check against a corporate actions calendar must be implemented to detect splits and invalidate cached filters accordingly.

Look-Ahead Bias Elimination: Calculate Z-scores using trailing-window metrics (shifted by 1) to eliminate look-ahead bias.

3. Risk, Friction & Compliance Guards
Circuit Breakers: The Orchestrator must track API timeouts; upon 3 consecutive evaluation failures, the bot must enter 'DEGRADED_MODE'. In this mode, new entries are halted but existing stop-losses are maintained.

EU Compliance Mapping: Hardcode UCITS equivalents for DEFCON 1 hedging (SPY -> XSPS.L, QQQ -> SQQQ.L, IWM -> R2SC.L). If an asset has no mapped equivalent, bypass the hedge and log a critical alert.

Micro-Budget Capital Preservation: Trades under $5.00 must be rejected with a 'FRICTION_REJECT' status if the calculated spread or fee exceeds 1.5%.

Flash-Crash Slippage Guards: All fractional market orders must include a limitPrice parameter set to 1% worse than the current price (1.01 for Buys, 0.99 for Sells).

DRIP Safety: Dividend reinvestment logic must cap execution value at the minimum of the gross dividend and available free cash to account for withholding taxes.

4. System Architecture & State Persistence
Kalman State Persistence: The ArbitrageService must persist and reload Kalman Filter state matrices (Mean and Covariance) using a local database/Redis to survive Docker restarts without requiring a warmup period.

Database Lock Handling: Implement a retry-with-backoff strategy for SQLite persistence to handle occasional database locks during concurrent write operations.

Timezone & Clock Sync: Operation hours in config.py must explicitly utilize pytz or zoneinfo tied to 'America/New_York' market hours to prevent DST drift. The ArbitrageMonitor must verify hour transitions every 15 minutes and check for early market closures.

LLM Hallucinations: AI Agents must use robust JSON extraction patterns to successfully handle LLM markdown wrapper hallucinations.