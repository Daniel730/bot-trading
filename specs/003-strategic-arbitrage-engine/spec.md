# Feature Specification: Strategic Arbitrage Engine

**Feature Branch**: `003-strategic-arbitrage-engine`  
**Created**: 2026-03-27  
**Status**: Draft  
**Input**: User description: "Criar a especificação para o motor de arbitragem estratégica. O sistema deve: 1. Monitorizar pares de ativos cointegrados (ex: KO/PEP) utilizando janelas móveis de Z-Score (30, 60, 90 dias).[2, 3] 2. Implementar gatilhos dinâmicos: Entrada quando $|Z| > 2.5$ e saída quando $|Z| < 0.5$. 3. Integração Quant-Fundamental: Ao atingir o gatilho estatístico, o Gemini CLI deve pesquisar notícias recentes (SEC filings, Earnings) para validar se a divergência é um ruído técnico ou uma mudança estrutural.[4, 5] 4. Gestão de \"Pie Virtual\": Simular o comportamento de rebalanceamento automático da Trading 212 via ordens de mercado individuais de \"Quantity\", respeitando a moeda base da conta.[6, 7] 5. Modo \"Paper Trading\": Permitir execução simulada para validação de estratégia antes do Live."

## Clarifications

### Session 2026-03-28
- Q: How should the system persist the "Virtual Pie" state, "Arbitrage Pair" configurations, and the "Simulated Ledger" for auditability? → A: Local SQLite database (Relational, ACID compliant).
- Q: What is the preferred mechanism for the "Human-in-the-loop" approval of trades before they are executed? → A: Telegram bot with interactive approval buttons.
- Q: How should the system handle price execution drift if the market price moves significantly between the AI validation/User approval and the actual order execution? → A: Configurable slippage tolerance % (Abort if exceeded).
- Q: How should the system behave if one asset in a pair has temporarily halted trading or has zero liquidity (FR-006)? → A: Abort entire rebalance (Leg-dependency safety).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Statistical Monitoring and Signal Generation (Priority: P1)

As a quantitative trader, I want the system to continuously monitor pairs of cointegrated assets and calculate their price relationship (Z-Score) across multiple timeframes, so that I can identify statistically significant deviations from the mean.

**Why this priority**: This is the core engine of the strategy. Without accurate statistical monitoring, no arbitrage opportunities can be detected.

**Independent Test**: Can be fully tested by providing a historical dataset of two assets and verifying that the Z-Score calculations for 30, 60, and 90-day windows match the expected mathematical values.

**Acceptance Scenarios**:

1. **Given** a pair of assets (e.g., KO and PEP), **When** the price ratio deviates such that $|Z| > 2.5$ on any configured window, **Then** an entry signal is generated.
2. **Given** an active arbitrage position, **When** the ratio reverts such that $|Z| < 0.5$ on the trigger window, **Then** an exit signal is generated.

---

### User Story 2 - Fundamental Validation via AI (Priority: P1)

As a trader, I want statistical signals to be validated against recent news and financial filings using AI, so that I can avoid "value traps" where a price divergence is caused by a fundamental change rather than technical noise.

**Why this priority**: Essential for risk management. Prevents the bot from trading against a permanent structural change in one of the assets (e.g., bankruptcy, fraud, merger).

**Independent Test**: Can be tested by simulating a signal and verifying that the system retrieves and analyzes the correct SEC filings and earnings news for the involved tickers before proceeding to the execution phase.

**Acceptance Scenarios**:

1. **Given** a statistical entry signal ($|Z| > 2.5$), **When** the system analyzes recent filings/news, **Then** it must provide a "Valid" or "Invalid" recommendation based on whether the divergence is technical or structural.
2. **Given** a "Structural Change" detection (e.g., a major lawsuit or profit warning), **When** the signal is processed, **Then** the trade must be suppressed and the reason logged.

---

### User Story 3 - Virtual Pie Execution and Rebalancing (Priority: P2)

As a user of Trading 212, I want my arbitrage trades to be executed as individual market orders that simulate the behavior of an automated "Pie," so that I can manage my portfolio weights accurately even when native Pie API features are limited.

**Why this priority**: Translates the mathematical strategy into actual market positions.

**Independent Test**: Can be tested by triggering a validated signal and verifying that the system calculates and executes the correct quantities for both assets to achieve the target rebalance in the base currency of the account.

**Acceptance Scenarios**:

1. **Given** a validated arbitrage signal, **When** execution is triggered, **Then** the system must calculate and send market orders for specific quantities of Asset A and Asset B.
2. **Given** an execution request, **When** orders are sent, **Then** they must respect the account's base currency and current balance constraints.

---

### User Story 4 - Paper Trading and Strategy Validation (Priority: P1)

As a developer/trader, I want run the entire strategy in a simulated environment using live market data without committing real capital, so that I can verify the logic and performance before going live.

**Why this priority**: Critical for safety and verification in a financial system. Allows for full system testing without financial risk.

**Independent Test**: Can be tested by enabling "Paper Trading" mode and verifying that all signals, validations, and "trades" are logged and tracked in a virtual ledger without sending orders to the live brokerage API.

**Acceptance Scenarios**:

1. **Given** Paper Trading mode is enabled, **When** a trade is "executed," **Then** no actual orders are sent to the brokerage, but the local "Virtual Pie" state is updated to reflect the simulated position.

### Edge Cases

- **Connectivity Issues**: What happens when the news/filings source or brokerage API is unreachable during signal validation?
- **Extreme Volatility**: Rapid price movements between signal generation and approval are handled by the slippage tolerance check (FR-011), aborting trades if the threshold is exceeded.
- **Zero Liquidity**: If one asset in a pair is halted or illiquid, the entire rebalance operation MUST be aborted to maintain leg-dependency and avoid unhedged exposure.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST monitor pairs of assets and calculate Z-Scores for 30, 60, and 90-day moving windows.
- **FR-002**: System MUST trigger an entry signal when $|Z| > 2.5$ and an exit signal when $|Z| < 0.5$.
- **FR-003**: System MUST automatically retrieve and analyze recent SEC filings and earnings news using Gemini CLI upon signal generation.
- **FR-004**: System MUST suppress execution if the AI validation identifies a "Structural Change" (fundamental event) rather than "Technical Noise."
- **FR-005**: System MUST maintain a local "Virtual Pie" state representing the target and current allocations for each asset.
- **FR-006**: System MUST execute rebalancing via individual market "Quantity" orders via the brokerage API.
- **FR-007**: System MUST support a "Paper Trading" toggle that prevents live order execution while maintaining all other logic.
- **FR-008**: System MUST perform all currency calculations based on the account's primary base currency.
- **FR-009**: System MUST persist all configurations, signals, and ledger entries in a local SQLite database.
- **FR-010**: System MUST send an asynchronous notification via Telegram for every validated signal and wait for manual approval/rejection via interactive buttons before executing any trade (Live or Paper).
- **FR-011**: System MUST verify that the current market price is within a configurable slippage tolerance percentage from the signal price before executing any market order.
- **FR-012**: If one leg of a two-part arbitrage swap fails to execute after the other leg has completed, the system MUST immediately halt further automated operations for that pair and send a high-priority alert via Telegram for manual intervention.

### Key Entities

- **Arbitrage Pair**: Cointegrated assets and their statistical parameters (mapped to SQLite table).
- **Z-Score Window**: Timeframes (30, 60, 90 days) for calculations (stored in historical records).
- **Validation Report**: Gemini CLI output recommendation (persisted in Signal history).
- **Virtual Pie Asset**: Record of ticker quantity and target weight (mapped to state table).
- **Simulated Ledger**: Immutable audit log of virtual trades and balance changes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Z-Score calculation matches reference statistical models with 99.9% accuracy.
- **SC-002**: News retrieval and AI analysis for a signal is completed in under 30 seconds.
- **SC-003**: Zero live orders are sent when the system is in "Paper Trading" mode.
- **SC-004**: Portfolio drift between "Virtual Pie" target and actual brokerage positions is less than 0.5% after a successful rebalance.

## Assumptions

- The system has access to a reliable real-time or near-real-time market data feed for asset prices.
- The Gemini CLI is configured with the necessary API keys and permissions to perform web searches and analysis.
- The brokerage API (Trading 212) supports individual market orders by quantity.
- Cointegration between asset pairs is verified externally before being added to the system.
- SEC filings and earnings news are available in English or Portuguese for analysis.
