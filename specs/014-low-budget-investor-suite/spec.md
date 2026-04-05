# Feature Specification: Low-Budget Investor Suite & Portfolio Manager

**Feature Branch**: `014-low-budget-investor-suite`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "Implement Low-Budget Investing and Portfolio Manager features for retail-focused wealth building and capital efficiency."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Micro-Budget Fractional Investing (Priority: P1)

As a retail investor with limited capital, I want to invest small fiat amounts (e.g., $10) into expensive stocks or ETFs using fractional shares, so that I can build a diversified portfolio without needing thousands of dollars upfront.

**Why this priority**: This is the core "low-budget" enabler. Without fractional shares, many assets are inaccessible to small accounts.

**Independent Test**: Can be tested by placing an order for a specific dollar amount (e.g., $15 of TSLA) and verifying the system calculates the correct fractional quantity and executes via the brokerage API.

**Acceptance Scenarios**:

1. **Given** a user wants to buy $10 of an asset, **When** they submit the request via the terminal, **Then** the system MUST calculate the equivalent fractional units based on current market price and route the order as a "value-based" trade.
2. **Given** a trade request for $10, **When** the asset price is $200, **Then** the system MUST attempt to purchase 0.05 units.

---

### User Story 2 - Automated DCA & Portfolio Management (Priority: P2)

As a long-term investor, I want to set up an automated Dollar-Cost Averaging (DCA) schedule that distributes my weekly micro-budget across a "safe" or "growth" portfolio, so that I can grow my wealth consistently with minimal effort.

**Why this priority**: Automation is key to the "wealth building" aspect of the investor persona.

**Independent Test**: Can be tested by scheduling a recurring $20 investment and verifying the "Portfolio Manager" agent correctly allocates it according to the selected risk profile on the scheduled date.

**Acceptance Scenarios**:

1. **Given** a recurring schedule of $15 every Friday, **When** Friday arrives, **Then** the system MUST trigger the Portfolio Manager to distribute the $15 across the target assets.
2. **Given** a "safe" risk profile, **When** the Portfolio Manager allocates funds, **Then** it MUST prioritize low-volatility ETFs over high-risk speculative stocks.

---

### User Story 3 - Explainable Investment Thesis (Priority: P3)

As an inquisitive investor, I want to ask "Why did we buy AAPL today?" and receive a natural language explanation, so that I can understand the logic behind my automated investments.

**Why this priority**: Enhances trust and provides the "Advisor" feel requested in the persona description.

**Independent Test**: Can be tested by querying the bot for a recent trade's justification and verifying it returns a coherent explanation combining fundamental and technical signals.

**Acceptance Scenarios**:

1. **Given** a trade was executed for AAPL, **When** the user asks "Why?", **Then** the system MUST generate a summary mentioning specific signals (e.g., "Strong balance sheet" or "Oversold RSI").

---

### Edge Cases

- **Insufficient Micro-Cash**: What happens when a $0.40 dividend is received but the minimum trade size is $1.00? (Assumption: System MUST queue micro-cash until it hits the minimum threshold for reinvestment).
- **Extreme Fee Impact**: How does the system handle a $5 trade where the flat fee is $1? (Action: System MUST auto-reject the trade as fees exceed the 1-2% threshold).
- **Market Closed**: How does DCA handle a Friday where the market is closed? (Assumption: System MUST execute on the next available trading day).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support "Value-Based" ordering (buying $X of an asset) in addition to "Quantity-Based" ordering.
- **FR-002**: System MUST include a **Fee Analyzer** that calculates total friction (spread, commission, FX fees) before execution.
- **FR-003**: System MUST auto-reject any trade where total friction costs exceed a default of 1.5% of the total trade value. This threshold MUST be user-configurable via settings.
- **FR-004**: System MUST provide a **DCA Service** allowing users to define recurring investment amounts and frequencies (daily, weekly, monthly).
- **FR-005**: System MUST include a **Dividend Reinvestment (DRIP)** feature that sweeps dividends back into fractional positions once a minimum threshold is met.
- **FR-006**: System MUST implement a **Portfolio Manager Agent** that acts as an orchestrator, translating user goals (Risk Tolerance, Age, Goals) into trading strategies.
- **FR-007**: System MUST implement a **Macro Economic Agent** that monitors interest rates and inflation, providing context to the Portfolio Manager.
- **FR-008**: System MUST generate a natural language **Investment Thesis** for every executed trade, logged and retrievable via the terminal.
- **FR-009**: Telegram Terminal MUST support natural language commands for micro-investments (e.g., "Invest $20 into something safe").

### Key Entities *(include if feature involves data)*

- **Portfolio Strategy**: Represents a collection of target assets, weights, and risk profiles (Conservative, Balanced, Growth).
- **DCA Schedule**: Stores the frequency, amount, and target strategy for recurring investments.
- **Investment Thesis**: A log entry containing the natural language justification for a trade, linked to specific agent signals.
- **Fee Configuration**: Stores the maximum allowed friction percentage and specific fee structures per brokerage.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can execute a fractional trade of $10 in under 5 seconds from the Telegram terminal.
- **SC-002**: 100% of trades with friction costs > 2% are automatically intercepted and rejected.
- **SC-003**: Automated DCA orders are executed within 60 minutes of the scheduled time.
- **SC-004**: "Investment Thesis" summaries are generated for 100% of bot-initiated trades.
- **SC-005**: 100% of dividends exceeding $1.00 are reinvested within 24 hours of the next market opening.

## Assumptions

- **Brokerage Support**: Assumes the underlying brokerage (Trading 212) API supports fractional shares and market orders by value.
- **Risk Profiles**: Assumes three default profiles: Conservative (Bonds/Cash), Balanced (ETFs/Large Cap), and Growth (High-growth equity).
- **Minimum Trade**: Assumes a minimum trade value of $1.00 for fractional shares.
- **Stable Macros**: Assumes Macro Economic data is updated at least once daily.
