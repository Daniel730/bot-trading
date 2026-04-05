# Feature Specification: Investor Suite Architectural Enforcement

**Feature Branch**: `016-investor-suite-enforcement`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "Critically update the specification documentation for the low-budget investor suite to enforce the following architectural rules and bug fixes: 1. Math: Statistical Arbitrage OLS regression MUST use an intercept (sm.add_constant) to avoid false cointegration positives. 2. Brokerage Safety: Pending market orders MUST NOT evaluate to $0.00 commitment; they must fallback to `data_service.get_latest_price`. 3. Risk: Friction calculations MUST correctly convert flat spread inputs into percentage-based values before validating against MAX_FRICTION_PCT. 4. Execution Limits: Value-based orders MUST validate calculated quantities against Trading 212's `minTradeQuantity` and `quantityIncrement` instrument metadata. 5. Compliance: The DEFCON 1 auto-hedger MUST include regional fallbacks (e.g., EU UCITS inverse ETFs) to prevent 403 Forbidden errors. 6. Stability: The multi-agent orchestrator MUST use return_exceptions=True or try/except blocks in asyncio.gather to prevent complete system crashes."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reliable Statistical Arbitrage (Priority: P1)

As a quantitative analyst, I want the statistical arbitrage engine to use an intercept in its OLS regressions so that I can avoid false cointegration positives that lead to bad trades.

**Why this priority**: Preventing false positives is critical to capital preservation in arbitrage strategies.

**Independent Test**: Can be tested by running the OLS regression against two non-cointegrated series that would otherwise show false cointegration without an intercept.

**Acceptance Scenarios**:

1. **Given** two price series for a pair, **When** the statistical arbitrage engine calculates cointegration, **Then** it must include an intercept (constant) in the OLS regression.
2. **Given** a pair that appears cointegrated only due to a non-zero mean spread, **When** analyzed with an intercept, **Then** it should be correctly identified as non-cointegrated (or have an adjusted Z-score).

---

### User Story 2 - Safe Order Execution (Priority: P1)

As a trader, I want my pending market orders to always have a valid commitment value, falling back to the latest price if necessary, to ensure that my risk management and budget checks are accurate.

**Why this priority**: Prevents the system from "thinking" an order costs $0.00, which could lead to over-leveraging or failed trades.

**Independent Test**: Simulate a market order where the initial commitment calculation returns $0.00 and verify it falls back to the data service price.

**Acceptance Scenarios**:

1. **Given** a pending market order, **When** the estimated commitment is calculated, **Then** it must NOT be $0.00.
2. **Given** a market order with missing pricing data from the broker, **When** calculating commitment, **Then** it must use `data_service.get_latest_price` as a fallback.

---

### User Story 3 - Robust Multi-Agent Orchestration (Priority: P2)

As a system administrator, I want the multi-agent orchestrator to be resilient to individual agent failures so that a single crashing agent doesn't take down the entire trading bot.

**Why this priority**: System stability is paramount for 24/7 trading operations.

**Independent Test**: Manually trigger an exception in one agent during an `asyncio.gather` call and verify other agents continue to process.

**Acceptance Scenarios**:

1. **Given** multiple agents running in parallel via `asyncio.gather`, **When** one agent raises an exception, **Then** the orchestrator must capture the exception and allow other agents to complete.
2. **Given** a failed agent task, **When** the orchestrator processes results, **Then** it must log the failure without crashing the main loop.

---

### User Story 4 - Compliant Global Hedging (Priority: P2)

As an international investor, I want the DEFCON 1 auto-hedger to use regional fallbacks for inverse ETFs so that I don't encounter "403 Forbidden" errors when trying to hedge positions in restricted jurisdictions (like the EU).

**Why this priority**: Ensures the "nuclear option" (hedging) works regardless of the user's location.

**Independent Test**: Attempt to trigger a hedge in an EU-simulated environment and verify it selects a UCITS-compliant inverse ETF.

**Acceptance Scenarios**:

1. **Given** a DEFCON 1 emergency trigger, **When** selecting a hedge instrument, **Then** it must check for regional availability/compliance.
2. **Given** a user in the EU, **When** the auto-hedger triggers, **Then** it must prefer EU UCITS inverse ETFs over US-only instruments to avoid 403 errors.

---

### Edge Cases

- **T212 Metadata Latency**: What happens when Trading 212 instrument metadata (`minTradeQuantity`, `quantityIncrement`) is temporarily unavailable during order validation?
- **Extreme Volatility**: How does the `get_latest_price` fallback handle situations where the spread between the last price and the execution price is extremely high?
- **Total Agent Wipeout**: How does the orchestrator handle the case where *all* agents in an `asyncio.gather` call return exceptions?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Statistical Arbitrage engine MUST include a mathematical intercept (constant term) in all OLS regressions used for cointegration testing to prevent false positive signals.
- **FR-002**: Market order valuation logic MUST NOT allow a $0.00 commitment; if the initial estimate is zero, it MUST fetch the latest price from a reliable data service as a fallback.
- **FR-003**: Friction calculations MUST convert flat spread inputs into percentage values based on current price before comparison against risk limits.
- **FR-004**: Value-based order generation MUST validate the final quantity against minimum trade size and increment constraints provided by the brokerage metadata.
- **FR-005**: The DEFCON 1 auto-hedger MUST implement regional fallbacks (e.g., UCITS-compliant instruments for EU regions) to ensure execution in restricted jurisdictions.
- **FR-006**: The multi-agent orchestrator MUST be configured to capture exceptions in individual agent tasks, preventing a single failure from terminating the entire concurrent execution.

### Key Entities *(include if feature involves data)*

- **Order Metadata**: Includes `minTradeQuantity`, `quantityIncrement`, and estimated commitment.
- **Instrument**: Represents a tradable asset with regional compliance flags (e.g., UCITS-eligible).
- **Agent Result**: The output of an agent's execution, which may be a success value or an error object.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% reduction in "403 Forbidden" errors during auto-hedger execution in EU-based simulations.
- **SC-002**: All Statistical Arbitrage pair selections must pass a cointegration test that specifically includes a constant term.
- **SC-003**: Zero instances of "Order size 0" errors for value-based orders due to T212 increment violations.
- **SC-004**: System uptime remains at 100% during simulated single-agent crashes within the multi-agent orchestrator.

## Assumptions

- **Data Service Availability**: `data_service.get_latest_price` is reliable and has higher availability than the brokerage's pending order valuation endpoint.
- **Brokerage API Support**: Trading 212 API provides reachable endpoints for `minTradeQuantity` and `quantityIncrement` metadata.
- **Regional Detection**: The system can accurately determine the user's regulatory region (e.g., via config or account metadata).
- **Standard Libraries**: `statsmodels` is the primary library for OLS; if not, an equivalent intercept mechanism is available.
