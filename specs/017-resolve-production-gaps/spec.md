# Feature Specification: Resolve Production Rigor Gaps

**Feature Branch**: `017-resolve-production-gaps`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "Update the specification to resolve the gaps identified in the production_rigor.md checklist. Enforce the following concrete rules: 1. Throttling & Fallbacks (CHK001, CHK002, CHK013): For data_service price fallbacks, implement a maximum of 3 retry attempts with exponential backoff (1s, 2s, 4s). If both the broker and data_service return 0.0, the calculation must immediately fail and the order must be rejected. 2. Circuit Breakers (CHK003): If the Orchestrator's multi-agent evaluation fails 3 consecutive times due to API timeouts, the bot MUST enter 'DEGRADED_MODE', halting all new entries while maintaining existing stop-losses. 3. EU Compliance Mapping (CHK004, CHK015): Hardcode the following UCITS equivalents for DEFCON 1 hedging: SPY -> XSPS.L, QQQ -> SQQQ.L, IWM -> R2SC.L. If an asset has no mapped UCITS equivalent, the hedge is bypassed, and a critical alert is logged. 4. Micro-Budget Friction (CHK005, CHK010): For trades under $5.00, if the calculated spread or fee exceeds the 1.5% maximum (e.g., >$0.03 on a $2.00 trade), the trade must be strictly rejected with a 'FRICTION_REJECT' status. No exceptions. 5. Quantitative Math (CHK006): The Statistical Arbitrage OLS regression MUST explicitly use `statsmodels.api.add_constant()` to establish the mathematical intercept."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resilient Price Retrieval (Priority: P1)

As a trading bot, I want to retry price fetching with exponential backoff when the primary data source fails, so that I don't miss trade opportunities due to transient network issues while avoiding API spam.

**Why this priority**: Accurate pricing is fundamental to all trading logic and risk management.

**Independent Test**: Simulate a transient network failure for the first two attempts and verify the system successfully retrieves the price on the third attempt after correct wait intervals.

**Acceptance Scenarios**:

1. **Given** a price request fails, **When** the system retries, **Then** it must use exponential backoff (1s, 2s, 4s).
2. **Given** all 3 retries fail and the broker price is also 0.0, **When** calculating order value, **Then** the order must be rejected immediately.

---

### User Story 2 - System Protection via Circuit Breaker (Priority: P1)

As a system administrator, I want the bot to enter a degraded mode if external APIs are consistently timing out, so that I can prevent erroneous trades while protecting existing positions.

**Why this priority**: Prevents the system from operating blindly or making poor decisions during major API outages.

**Independent Test**: Trigger 3 consecutive API timeouts in the Orchestrator and verify the system status changes to 'DEGRADED_MODE' and blocks new trade entries.

**Acceptance Scenarios**:

1. **Given** 3 consecutive multi-agent evaluation timeouts, **When** the system processes the next signal, **Then** it must transition to 'DEGRADED_MODE'.
2. **Given** the system is in 'DEGRADED_MODE', **When** a new trade signal is generated, **Then** the entry must be blocked, but existing stop-losses must remain active.

---

### User Story 3 - Compliant EU Hedging (Priority: P2)

As an EU-based investor, I want the auto-hedger to use UCITS-compliant instruments for common indices, so that I avoid regulatory rejections and can effectively manage risk.

**Why this priority**: Required for operational legality and risk management in the EU region.

**Independent Test**: Trigger a DEFCON 1 hedge for a SPY position in an EU environment and verify it selects XSPS.L.

**Acceptance Scenarios**:

1. **Given** a position in SPY, QQQ, or IWM, **When** a DEFCON 1 hedge is triggered in the EU, **Then** it must select the mapped UCITS equivalent (XSPS.L, SQQQ.L, R2SC.L respectively).
2. **Given** an asset with no UCITS mapping, **When** hedging is triggered, **Then** the hedge must be bypassed and a critical alert logged.

---

### User Story 4 - Micro-Budget Capital Preservation (Priority: P1)

As a low-budget investor, I want my micro-trades to be strictly rejected if fees and spreads consume too much of my capital, so that I don't lose money to friction.

**Why this priority**: Friction can easily exceed expected returns on very small trades.

**Independent Test**: Attempt a $2.00 trade where total friction is $0.04 and verify it is rejected with 'FRICTION_REJECT'.

**Acceptance Scenarios**:

1. **Given** a trade amount under $5.00, **When** calculated friction exceeds 1.5%, **Then** the trade must be rejected with status 'FRICTION_REJECT'.

---

### User Story 5 - Statistically Sound Modeling (Priority: P1)

As a quantitative analyst, I want the arbitrage engine to use a proper mathematical intercept in its regressions, so that cointegration signals are accurate and not biased by a non-zero mean.

**Why this priority**: Prevents false positive signals that lead to loss-making "arbitrage" trades.

**Independent Test**: Run a cointegration test on two series with a constant offset and verify the regression results include a non-zero intercept and a correct hedge ratio.

**Acceptance Scenarios**:

1. **Given** two price series for OLS regression, **When** calculating the hedge ratio, **Then** `statsmodels.api.add_constant()` must be used on the independent variable.

---

### Edge Cases

- **Partial Recovery**: What happens if 2 timeouts occur, then a success, then another timeout? (Circuit breaker should reset on success).
- **Simultaneous Failures**: How does the system handle a price failure while already in 'DEGRADED_MODE'? (Degraded mode logic takes precedence).
- **Mixed Jurisdictions**: How are assets handled that are already UCITS compliant? (No mapping needed, use original).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `data_service` MUST implement a retry policy for price fallbacks: max 3 attempts, exponential backoff at 1s, 2s, and 4s.
- **FR-002**: If both primary broker and `data_service` return 0.0 for a price, the system MUST reject the associated order.
- **FR-003**: The Orchestrator MUST track consecutive API timeouts. Upon the 3rd consecutive timeout, the system MUST transition to `DEGRADED_MODE`.
- **FR-004**: In `DEGRADED_MODE`, the system MUST block all new position entries but MUST allow the execution/maintenance of existing stop-loss and take-profit orders.
- **FR-005**: The auto-hedger MUST use the following mappings for EU UCITS compliance: SPY -> XSPS.L, QQQ -> SQQQ.L, IWM -> R2SC.L.
- **FR-006**: If a DEFCON 1 hedge is required for an asset without a UCITS mapping, the system MUST bypass the hedge and log a CRITICAL alert.
- **FR-007**: Trades under $5.00 MUST be rejected with status `FRICTION_REJECT` if the calculated friction (spread + fees) exceeds 1.5% of the trade value.
- **FR-008**: All OLS regressions in the Statistical Arbitrage engine MUST include a constant term using `statsmodels.api.add_constant()`.

### Key Entities *(include if feature involves data)*

- **System Status**: Enum including `NORMAL` and `DEGRADED_MODE`.
- **Hedge Mapping**: A dictionary/lookup table for regional compliance.
- **Friction Result**: Data structure containing status (`FRICTION_REJECT` or `ACCEPTED`) and percentage.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of price fallback attempts follow the 1s, 2s, 4s backoff schedule.
- **SC-002**: Zero "spam" requests to data APIs after the 3rd failed retry within a single operation.
- **SC-003**: System transitions to `DEGRADED_MODE` within 1 second of the 3rd consecutive timeout.
- **SC-004**: 100% of EU-based hedges for SPY/QQQ/IWM use the specified UCITS tickers.
- **SC-005**: Zero trades under $5.00 executed with >1.5% friction.
- **SC-006**: Statistical Arbitrage regressions show a non-zero intercept for series with constant offsets.

## Assumptions

- **Time Consistency**: The system clock is accurate for calculating backoff intervals.
- **Persistence**: Consecutive failure counts are reset upon system restart or a successful execution.
- **Region Detection**: The bot can correctly identify the user's regulatory jurisdiction (US vs EU).
