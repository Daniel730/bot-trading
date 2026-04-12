# Feature Specification: Dynamic Risk and Volatility Switch

**Feature Branch**: `028-dynamic-risk-and-volatility-switch`  
**Created**: 2026-04-06  
**Status**: Draft  
**Input**: User description: "1. Implement dynamic position sizing in the Python Orchestrator driven by the real-time portfolio Sharpe ratio and maximum drawdown. 2. Architect a Volatility Switch that monitors real-time L2 order book entropy. 3. The Python brain must dynamically update the maxSlippage tolerance on the Java ExecutionEngine via gRPC when the Volatility Switch is triggered. 4. Utilize the ongoing DEV_MODE crypto testing data to baseline these risk thresholds."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dynamic Position Sizing (Priority: P1)

As a portfolio manager, I want the system to automatically reduce position sizes when the portfolio's Sharpe ratio declines or maximum drawdown increases, so I can preserve capital during periods of low alpha or high market stress.

**Why this priority**: Directly addresses Principle I (Capital Preservation) by scaling risk based on empirical performance.

**Independent Test**: Simulate a series of losing trades (drawdown) and verify that the `KellyCalculator` in `risk_service.py` outputs progressively smaller position multipliers.

**Acceptance Scenarios**:

1. **Given** a 10% portfolio drawdown, **When** a new trade signal is generated, **Then** the position size must be reduced by at least 25% compared to the baseline size.
2. **Given** a Sharpe ratio < 0.5, **When** calculating trade size, **Then** the Kelly fraction must be capped at 0.1 (DEFCON 2).

---

### User Story 2 - Volatility Switch (Priority: P1)

As a quant analyst, I want the system to monitor L2 order book entropy (the randomness of bids/asks) to detect impending volatility spikes, so I can adjust execution parameters before the spread widens.

**Why this priority**: Prevents getting caught in "toxic flow" or illiquid market spikes.

**Independent Test**: Use high-frequency crypto data (BTC-USD) in DEV_MODE to identify periods where entropy > 0.8 and verify the `VolatilitySwitch` triggers.

**Acceptance Scenarios**:

1. **Given** a sudden increase in L2 order book entropy (bids/asks disappearing or flickering), **When** a trade is about to be sent, **Then** the `VolatilitySwitch` status must change to `HIGH_VOLATILITY`.

---

### User Story 3 - Dynamic gRPC Slippage Adjustment (Priority: P1)

As an execution engineer, I want the Python Orchestrator to dynamically tighten or loosen the `maxSlippage` parameter in the Java Execution Engine based on the `VolatilitySwitch` status, so we can ensure fills only happen when price stability is sufficient.

**Why this priority**: Hardening the "Muscle" (Java Engine) against market noise.

**Acceptance Scenarios**:

1. **Given** `VolatilitySwitch` is `HIGH_VOLATILITY`, **When** sending a gRPC `ExecuteTrade` request, **Then** the `max_slippage_pct` must be reduced (e.g., from 0.001 to 0.0005) to prevent execution in a widening spread.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST track daily portfolio returns, cumulative drawdown, and rolling 30-day Sharpe ratio in PostgreSQL.
- **FR-002**: `RiskService` MUST adjust the `KellyCalculator` multiplier using a performance-based scaler: `RiskScale = f(Sharpe, MaxDrawdown)`.
- **FR-003**: System MUST implement a `VolatilitySwitchService` that calculates Shannon Entropy on L2 snapshots stored in Redis.
- **FR-004**: The `ExecutionServiceClient` (Python) MUST accept a dynamic `max_slippage` parameter derived from the `VolatilitySwitch`.
- **FR-005**: The Java Engine's `SlippageGuard` MUST enforce the dynamically provided `max_slippage_pct` without hardcoded overrides.
- **FR-006**: System MUST utilize `DEV_MODE` crypto pairs to baseline "High Entropy" thresholds.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Position size scales linearly with drawdown: 0% at 15% drawdown (Absolute Stop).
- **SC-002**: Volatility Switch identifies 95% of volatility spikes (> 2x average spread) within 5 seconds using L2 entropy.
- **SC-003**: gRPC `ExecuteTrade` requests reflect the correct `max_slippage_pct` based on real-time volatility status.
- **SC-004**: 0 trades executed in "Toxic Volatility" windows where entropy exceeds the 99th percentile baseline.

## Assumptions

- **L2 Feed Quality**: The L2 feed provides sufficient depth updates to calculate entropy reliably.
- **PostgreSQL Connectivity**: Historical returns are available in the `trade_ledger` or a new `portfolio_history` table.
- **DEV_MODE Stability**: Crypto data reflects similar order book dynamics (entropy-wise) to equities.
