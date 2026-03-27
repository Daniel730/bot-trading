# Feature Specification: Trading Arbitrage Bot with Virtual Pie and AI Validation

**Feature Branch**: `002-trading-arbitrage-bot`  
**Created**: 2026-03-27  
**Status**: Draft  
**Input**: User description: "Monitorização de Pares Cointegrados: O bot deve observar simultaneamente pares de empresas concorrentes (ex: AAPL vs MSFT, KO vs PEP). Motor de Decisão (Z-Score): Calcular o rácio de preço entre os dois ativos. Gerar um Z-Score baseado na média móvel de 30-60 dias. Gatilho de Troca: Se $Z > 2.0$ (Ativo A caro/Ativo B barato), sugerir/executar venda de A e compra de B. Se $Z < -2.0$, o oposto. Gestão de \"Pie Virtual\": Devido à depreciação dos endpoints de Pie na API da Trading 212, o bot deve manter uma base de dados local (JSON ou SQLite) com as alocações alvo, simulando o comportamento de uma Pie através de ordens individuais. Intervenção do Gemini CLI: Antes de cada execução, o bot deve enviar um resumo do contexto (ex: \"Z-Score atingiu 2.5\") para o Gemini CLI validar se existe alguma notícia macro ou evento fundamental que invalide a reversão técnica."

## Clarifications

### Session 2026-03-27
- Q: What is the intended number of simultaneous pairs the system should monitor? → A: 1 to 5 pairs (Small scale/Personal use).
- Q: Should trades execute immediately after AI approval, or is a final manual confirmation required? → A: Hybrid: AI validates signal, then requests manual confirmation via Telegram.
- Q: Should the bot rely entirely on its local database for "Current Quantity", or should it re-sync from the brokerage API on startup? → A: Hybrid: Load targets from local DB, but re-sync current quantities from brokerage API on startup.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Real-time Signal Monitoring (Priority: P1)

As an investor, I want the system to continuously track pairs of competitors so that I can identify statistical arbitrage opportunities based on relative price deviations.

**Why this priority**: Essential for the core strategy; the bot cannot act without detecting price anomalies.

**Independent Test**: Can be tested by providing historical data for two tickers and verifying the Z-score calculation matches the expected value based on the 30-60 day window.

**Acceptance Scenarios**:

1. **Given** a pair of stocks (e.g., AAPL/MSFT), **When** the current Z-score reaches 2.1, **Then** a sell signal for AAPL and a buy signal for MSFT is generated.
2. **Given** a pair of stocks, **When** the Z-score reaches -2.1, **Then** a buy signal for AAPL and a sell signal for MSFT is generated.

---

### User Story 2 - Contextual Validation and Oversight (Priority: P1)

As an investor, I want signals to be validated by an AI agent and then presented for my final confirmation, so that I maintain ultimate control over trade execution while leveraging automated analysis.

**Why this priority**: Core safety mechanism defined in the constitution and ensuring user-in-the-loop oversight for capital-intensive actions.

**Independent Test**: Can be tested by providing a signal, verifying the AI recommendation, and then simulating a user "Approve" or "Reject" response via the notification channel.

**Acceptance Scenarios**:

1. **Given** a Z-score signal of 2.5, **When** the AI approves the trade, **Then** a notification is sent to the user requesting final confirmation.
2. **Given** a confirmation request, **When** the user selects "Approve", **Then** the trade is executed.
3. **Given** a confirmation request, **When** the user selects "Reject", **Then** the signal is cancelled and logged.

---

### User Story 3 - "Virtual Pie" Execution (Priority: P2)

As an investor, I want the bot to manage my portfolio weights locally and execute individual orders, so that I can maintain my desired allocation despite the brokerage's API limitations.

**Why this priority**: Necessary workaround for the deprecated native Pie API; ensures the bot can actually implement the rebalancing.

**Independent Test**: Can be tested by simulating a rebalance signal and verifying that the local database reflects the target weights and correct individual market orders are queued.

**Acceptance Scenarios**:

1. **Given** a validated trade signal, **When** the bot executes the rebalance, **Then** it calculates the exact quantity of shares to sell from asset A and buy for asset B to reach the target allocation.
2. **Given** a system restart, **When** the bot initializes, **Then** it loads the current allocation state from the local database.

---

### User Story 4 - Market Hour Discipline (Priority: P1)

As an investor, I want the bot to strictly follow market hours so that I don't face execution issues or excessive slippage during low-liquidity periods.

**Why this priority**: Mandatory principle in the project constitution (Principle I).

**Independent Test**: Can be tested by attempting to trigger a signal at 21:15 WET and verifying that the order is rejected/not sent.

**Acceptance Scenarios**:

1. **Given** a validated signal, **When** the current time is 16:00 WET, **Then** the order is sent to the brokerage.
2. **Given** a validated signal, **When** the current time is 21:30 WET, **Then** the order is suppressed and an alert is logged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST monitor prices for up to 5 concurrent pairs of competitors.
- **FR-002**: System MUST calculate price ratios and Z-scores using a configurable 30-90 day lookback window.
- **FR-003**: System MUST store target allocations and current positions in a local database (SQLite).
- **FR-004**: System MUST trigger AI validation for any Z-score deviation exceeding |2.0| and request user confirmation via the notification interface before execution.
- **FR-005**: System MUST translate confirmed "Virtual Pie" rebalance actions into individual market orders (buy/sell) via the brokerage API.
- **FR-006**: System MUST enforce a strict operation window (14:30 - 21:00 WET/WEST).
- **FR-007**: System MUST implement a "Reserva Estratégica" model, limiting single-trade allocation based on configurable risk parameters.
- **FR-008**: System MUST send detailed notifications via Telegram before and after any trade attempt.

### Key Entities

- **Trading Pair**: Pair of stocks with their historical correlation data.
- **Virtual Pie**: Local representation of the portfolio (Ticker, Target Weight, Current Quantity).
- **Signal**: Data point containing Z-score, timestamp, and suggested action (Buy/Sell/Hold).
- **Audit Log**: Record of AI validations, decisions, and brokerage execution results.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Z-score calculation accuracy within 0.01 deviation from the reference mathematical model.
- **SC-002**: AI validation response time under 15 seconds.
- **SC-003**: 100% adherence to market hours; zero orders sent outside the 14:30-21:00 window.
- **SC-004**: "Virtual Pie" drift from target allocation reduced to <1% after each successful rebalance.

## Assumptions

- SQLite is used for local state persistence.
- The user has provided valid API credentials for the brokerage and Telegram.
- The AI agent has access to real-time or near-real-time market news feeds.
- "Reserva Estratégica" limit (X%) is defined in the `.env` configuration.
