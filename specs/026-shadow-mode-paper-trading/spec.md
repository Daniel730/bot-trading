# Feature Specification: Shadow Mode Paper Trading

**Feature Branch**: `026-shadow-mode-paper-trading`  
**Created**: 2026-04-06  
**Status**: Draft  
**Input**: User description: "feature="026-shadow-mode-paper-trading" context="execution-engine/src/main/java/com/arbitrage/engine/api/ExecutionServiceImpl.java,execution-engine/src/main/java/com/arbitrage/engine/broker/BrokerageRouter.java" requirements="1. Introduce a strict DRY_RUN environment variable. 2. If DRY_RUN is true, the BrokerageRouter must intercept fully validated atomic multi-leg requests and route them to a MockBroker implementation. 3. The MockBroker must simulate realistic fill prices using the current L2 OrderBook depth. 4. Persist these mock trades to the TradeLedgerRepository with a distinct 'PAPER' execution flag to prevent polluting real audit logs.""

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Risk-Free Strategy Validation (Priority: P1)

As a quantitative trader, I want to run my arbitrage strategies against real-time market depth without risking actual capital, so I can verify the profitability and logic of new algorithms before live deployment.

**Why this priority**: This is the core value proposition of the feature, enabling safe testing in production-like environments.

**Independent Test**: Can be fully tested by setting `DRY_RUN=true` and observing that trade requests generate database entries marked as 'PAPER' with realistic prices, while external brokerage logs show zero activity.

**Acceptance Scenarios**:

1. **Given** the bot is started with `DRY_RUN=true`, **When** an arbitrage signal triggers an atomic multi-leg trade, **Then** the `BrokerageRouter` routes the request to the `MockBroker` instead of the live exchange.
2. **Given** a paper trade is initiated, **When** the `MockBroker` calculates the fill price, **Then** it must account for the current L2 OrderBook liquidity to simulate slippage accurately.

---

### User Story 2 - Operational Safety Guard (Priority: P2)

As a system operator, I want a global "kill switch" for real trades that still allows the system to process signals and "execute" them in a sandbox, so I can perform maintenance or troubleshooting on the execution engine without financial risk.

**Why this priority**: Provides a safety layer during system upgrades or debugging sessions.

**Independent Test**: Verify that even if the `ExecutionServiceImpl` receives a valid request, it never reaches the live brokerage layer if the `DRY_RUN` flag is set.

**Acceptance Scenarios**:

1. **Given** `DRY_RUN=true`, **When** any part of the system attempts to execute a trade, **Then** a clear log message indicates "Shadow Mode Active" and no external API calls are made.

---

### Edge Cases

- **Insufficient Liquidity**: What happens when the paper trade size exceeds the available L2 OrderBook depth? (Assumption: Partial fill or rejection based on simulated "Fill or Kill" settings).
- **Data Delay**: How does the system handle stale L2 data when calculating paper prices? (Assumption: The trade is rejected or marked as "stale" if data is older than a specific threshold).
- **Persistence Failure**: If the `TradeLedgerRepository` fails to save a PAPER trade, should the engine halt? (Assumption: Log error but continue, as no real money was at risk).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST read the `DRY_RUN` environment variable at boot time and initialize the `BrokerageRouter` in "Shadow Mode" if set to `true`.
- **FR-002**: `BrokerageRouter` MUST intercept 100% of validated atomic multi-leg requests when in Shadow Mode.
- **FR-003**: `MockBroker` MUST implement the same interface as real brokers to ensure seamless routing.
- **FR-004**: `MockBroker` MUST retrieve real-time L2 OrderBook depth for all legs of an atomic trade to calculate a volume-weighted average price (VWAP) for the simulated fill.
- **FR-005**: System MUST persist every simulated execution to the `TradeLedgerRepository`.
- **FR-006**: Every paper trade record MUST contain a distinct `PAPER` flag or execution type to isolate it from real audit logs.
- **FR-007**: System MUST provide clear console/log feedback whenever a trade is routed to the MockBroker.

### Key Entities *(include if feature involves data)*

- **MockTrade**: Represents a simulated execution, containing symbol, quantity, simulated fill price, slippage, and timestamp.
- **TradeLedgerEntry**: Existing entity updated to support the `execution_mode` attribute (LIVE vs. PAPER).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero (0) real-money trades are executed on external exchanges when `DRY_RUN=true`.
- **SC-002**: Simulated fill prices deviate by less than 0.1% from the theoretical price derived from the L2 snapshot at the time of "execution".
- **SC-003**: 100% of PAPER trades are successfully persisted with the correct metadata and flag.
- **SC-004**: System latency in Shadow Mode (including L2 lookup and simulation) remains under 100ms per multi-leg request.

## Assumptions

- **L2 Data Availability**: The system has access to a real-time L2 data provider that the `MockBroker` can query.
- **Environment Parity**: The `DRY_RUN` mode uses the same validation and routing logic as the live mode, only swapping the final execution leg.
- **Single Mode**: The entire execution engine operates in either LIVE or PAPER mode based on the environment variable; per-trade mode switching is out of scope.
- **OrderBook Depth**: The `MockBroker` MUST use the existing `L2FeedService` (or project-standard market data provider) to retrieve the required depth data, ensuring parity with the live execution path.
