# Feature Specification: Production-Grade Polish & Reliability Enforcement

**Feature Branch**: `018-production-polish-rules`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "Critically update the specification documentation to enforce the following production-grade polish rules: 1. State Persistence: The ArbitrageService MUST persist and reload Kalman Filter state matrices using a local database/Redis to survive Docker restarts. 2. API Caching: The BrokerageService MUST implement a 5-second TTL cache for /portfolio and /orders endpoints to prevent 429 Rate Limit API bans. 3. Slippage Guards: All fractional market orders MUST include a limitPrice parameter set to 1% worse than the current data_service price to prevent flash-crash slippage. 4. DRIP Safety: Dividend reinvestment logic MUST cap execution value at min(gross_dividend, available_free_cash) to account for withholding taxes. 5. Timezone Sync: Operation hours in config.py MUST utilize pytz or zoneinfo explicitly tied to 'America/New_York' market hours to prevent DST drift."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resilience across System Restarts (Priority: P1)

As a trading system, I need to persist my mathematical model states (Kalman Filter matrices) so that I can resume trading immediately after a restart without a 30-60 minute data "warm-up" period.

**Why this priority**: Crucial for maintaining "always-on" reliability and preventing missed opportunities during deployment windows.

**Independent Test**: Kill the Docker container during active trading, restart it, and verify the `ArbitrageService` loads the exact same state matrices it had before the shutdown.

**Acceptance Scenarios**:

1. **Given** the bot is tracking a pair with a stabilized Kalman Filter, **When** the service is restarted, **Then** the initial Z-score and spread calculations MUST match the last recorded values before shutdown.
2. **Given** a new pair is added, **When** no prior state exists, **Then** the system MUST initialize a new state and begin persistence immediately.

---

### User Story 2 - API Rate Limit Protection (Priority: P2)

As an automated bot, I need to cache frequent data requests (portfolio/orders) so that I don't get banned by the brokerage API provider (429 errors) when multiple components or dashboard users request data simultaneously.

**Why this priority**: Prevents system-wide outages caused by API provider bans and improves dashboard responsiveness.

**Independent Test**: Trigger 10 rapid calls to the portfolio endpoint within 1 second and verify only 1 actual request is made to the external API provider.

**Acceptance Scenarios**:

1. **Given** a request for `/portfolio` was made 2 seconds ago, **When** a new request is made, **Then** the system MUST return the cached data.
2. **Given** a request for `/portfolio` was made 6 seconds ago, **When** a new request is made, **Then** the system MUST fetch fresh data from the provider.

---

### User Story 3 - Flash-Crash Slippage Protection (Priority: P2)

As a retail investor, I want my fractional market orders to have a "synthetic" limit price so that I am protected from paying 5-10% more than expected during moments of extreme market volatility.

**Why this priority**: Protects capital from "flash crashes" where market orders can be filled at absurdly unfavorable prices.

**Independent Test**: Simulate a market order placement and verify the underlying API call includes a `limitPrice` that is exactly 1% offset from the last quoted price.

**Acceptance Scenarios**:

1. **Given** a buy order for 0.5 shares of Ticker A at $100.00, **When** the order is sent, **Then** the `limitPrice` MUST be set to $101.00.
2. **Given** a sell order for 0.5 shares of Ticker A at $100.00, **When** the order is sent, **Then** the `limitPrice` MUST be set to $99.00.

---

### User Story 4 - Market Timezone Accuracy (Priority: P1)

As a systematic trader, I need the bot's operating hours to stay synchronized with the New York Stock Exchange regardless of Daylight Saving Time transitions or local server time settings.

**Why this priority**: Essential for legal compliance and preventing orders from being sent when markets are closed or in "thin" after-hours liquidity.

**Independent Test**: Set the server clock to a date before and after a DST transition and verify the "Market Open" logic triggers at exactly 9:30 AM ET in both cases.

**Acceptance Scenarios**:

1. **Given** it is 9:30 AM ET on a Monday, **When** the bot checks operation hours, **Then** it MUST transition to 'ACTIVE' status.
2. **Given** the server is running in UTC, **When** the bot calculates market open, **Then** it MUST correctly offset based on 'America/New_York' rules.

---

### Edge Cases

- **Persistence Corruption**: What happens when the stored Kalman state is corrupted or unreadable? (System MUST log the error, backup the corrupt file, and re-initialize from scratch).
- **Cache Invalidation**: How does the system handle an urgent "Order Fill" event that should invalidate the portfolio cache? (In this spec, we stick to a strict 5s TTL for simplicity, but manual refresh is an assumption).
- **Missing Data Feed**: What if the `data_service` is down when calculating the 1% slippage guard? (Order MUST be rejected/aborted).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `ArbitrageService` MUST persist Kalman Filter state (State Mean and Covariance matrices) to a local SQLite database or Redis instance after every update cycle.
- **FR-002**: `ArbitrageService` MUST attempt to load persisted matrices upon initialization before falling back to default identity matrices.
- **FR-003**: `BrokerageService` MUST implement a 5-second Time-To-Live (TTL) cache for `/portfolio` and `/orders` endpoints.
- **FR-004**: `BrokerageService` MUST include a `limitPrice` parameter for ALL fractional market orders, calculated as `current_price * 1.01` for Buys and `current_price * 0.99` for Sells.
- **FR-005**: Dividend Reinvestment (DRIP) logic MUST calculate the maximum allowed order value as the minimum of the gross dividend amount received and the currently available free cash.
- **FR-006**: The system MUST utilize `pytz` or `zoneinfo` with the 'America/New_York' key for all calculations involving market opening/closing times.
- **FR-007**: `ArbitrageService` MUST implement a covariance guard for Kalman Filters to detect `NaN` or `Inf` values and reset the state if detected.
- **FR-008**: `DataService` MUST fetch adjusted historical prices (splits/dividends) and detect corporate actions to invalidate stale filters.
- **FR-009**: `ArbitrageService` MUST calculate Z-scores using trailing-window metrics (shifted by 1) to eliminate look-ahead bias.
- **FR-010**: `BrokerageService` MUST track positions based on explicit execution reports/confirmations rather than requested quantities.
- **FR-011**: `BrokerageService` MUST implement idempotency keys (UUIDs) for all order placements to prevent duplicate executions on network timeouts.
- **FR-012**: `BrokerageService` MUST round order prices and quantities to match asset-specific tick sizes and increments provided by metadata.
- **FR-013**: AI Agents MUST use robust JSON extraction patterns to handle LLM markdown hallucinations.
- **FR-014**: `BrokerageService` MUST implement a "Single-Flight" pattern or lock for the API cache to prevent the "Thundering Herd" problem on high-frequency dashboard reloads.
- **FR-015**: `ArbitrageService` MUST implement a retry-with-backoff strategy for SQLite persistence to handle occasional database locks during concurrent write operations.
- **FR-016**: `ArbitrageMonitor` MUST verify and log market hour transitions every 15 minutes to handle the 2 AM DST shift without requiring a service restart.
- **FR-017**: `ArbitrageMonitor` MUST query an external market status API (or use a predefined calendar) to detect early market closures and halt operations accordingly.

### Key Entities *(include if feature involves data)*

- **KalmanState**: Represents the persisted mathematical state of a pair's spread calculation (Mean vector, Covariance matrix, timestamp).
- **CacheRegistry**: Internal mapping of endpoint paths to timestamps and serialized responses for rate-limit protection.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0% loss of Kalman convergence state across service restarts (verified by comparing Z-scores before/after).
- **SC-002**: 100% of 429 "Too Many Requests" errors eliminated during typical dashboard usage.
- **SC-003**: 100% of fractional market orders placed include a verified `limitPrice` slippage guard.
- **SC-004**: Zero instances of "Insufficient Funds" errors during automated dividend reinvestment.
- **SC-005**: Bot activation/deactivation occurs within ±1 second of 09:30:00 and 16:00:00 ET.

## Assumptions

- **Local Persistence**: A local SQLite file is sufficient for state persistence in the current Docker volume setup.
- **Precision**: Fractional share calculations will maintain at least 6 decimal places of precision before rounding for order placement.
- **Market Data**: The `data_service` is assumed to provide "live-enough" pricing for the 1% slippage calculation (within 500ms).
- **Tax Withholding**: The `min(gross_dividend, free_cash)` logic assumes that free cash is already net of any immediately withheld taxes if the broker handles them in real-time.
