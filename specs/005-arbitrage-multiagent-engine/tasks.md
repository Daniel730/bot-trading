# Tasks: Multi-Agent Arbitrage Engine

**Input**: Design documents from `/specs/005-arbitrage-multiagent-engine/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are recommended for the math engine and risk services.

**Organization**: Tasks are grouped by logical phases aligned with the technical plan and user stories.

## Phase 1: Infraestrutura base e conetividade MCP

**Purpose**: Project initialization, core models, and MCP tool exposure.

- [X] T001 Create project structure: `src/agents/`, `src/services/`, `src/models/`
- [X] T002 Initialize Python 3.12 project with `requirements.txt` (LangGraph, FastMCP, QuantStats, statsmodels, polygon-api-client)
- [X] T003 [P] Implement `src/models/persistence.py` with SQLite schemas for `ArbitragePair`, `Signal`, `TradeRecord`, and `ThoughtJournal`
- [X] T004 Implement `src/config.py` for environment variables and the 20 initial arbitrage pair definitions
- [X] T005 Implement `src/mcp_server.py` using FastMCP to expose `get_market_data` and `execute_trade` tools

---

## Phase 2: Motor matemático de StatArb (ADF/Z-Score)

**Purpose**: Implementation of the statistical monitoring logic and data acquisition.

**⚠️ CRITICAL**: This phase MUST be complete before the Cognitive Layer can process any signals.

- [X] T006 [P] Implement `src/services/data_service.py` with yfinance (history) and Polygon.io WebSocket (real-time) handlers
- [X] T007 Implement `src/services/arbitrage_service.py` with ADF test (cointegration) and dynamic Z-score calculation
- [X] T008 [US2] Implement the continuous monitoring loop in `src/monitor.py` to trigger signals when Z-score > ±2.0
- [X] T009 [P] Implement `src/services/risk_service.py` with Monte Carlo VaR calculation and Kelly Fractional sizing (0.25x)
- [X] T010 [P] Create unit tests for arbitrage math in `tests/unit/test_arbitrage_math.py`

**Checkpoint**: Foundation ready - the bot can now detect statistical deviations and calculate risk metrics.

---

## Phase 3: Camada de Inteligência Cognitiva (Agentes)

**Purpose**: Implementation of the LangGraph adversarial debate and shadow trading.

- [X] T011 [P] [US3] Implement `src/agents/news_analyst.py` using Gemini to detect "Event Spikes" (Earnings/SEC filings)
- [X] T012 [P] [US3] Implement `src/agents/bull_agent.py` and `src/agents/bear_agent.py` for signal validation
- [X] T013 [US3] Implement LangGraph orchestration in `src/agents/orchestrator.py` to coordinate the adversarial debate
- [X] T014 [US1] Implement `src/services/shadow_service.py` for Virtual Ledger management and PnL simulation
- [X] T015 [US1] Integrate Shadow Mode toggle in `src/monitor.py` to allow capital-free validation

**Checkpoint**: At this point, the bot can validate signals through AI debate and run in Shadow mode.

---

## Phase 4: Interface de Monitorização e Logs XAI

**Purpose**: Human-in-the-loop notifications, audit reports, and explainability logs.

- [X] T016 [US4] Implement Telegram bot in `src/services/notification_service.py` with inline buttons for trade approval ($100 threshold)
- [X] T017 [US3] Implement Thought Journal persistence in `src/services/audit_service.py` including SHAP/LIME importance placeholders
- [X] T018 [P] Implement daily HTML report generation in `src/services/audit_service.py` using QuantStats tearsheets
- [X] T019 Final integration: Connect Telegram approval flow into the `src/monitor.py` execution pipeline
- [X] T020 [P] Implement `/status` and `/stop` commands in the Telegram notification service

---

## Phase N: Polish & Cross-Cutting Concerns

- [X] T021 [P] Add detailed logging across all services following the Auditability Principle
- [X] T022 Implement strict NYSE/NASDAQ operating hours check (14:30-21:00 WET) in the main scheduler
- [X] T023 Run `quickstart.md` validation to ensure environment setup is seamless
- [X] T024 Performance optimization: Ensure decision latency is < 10s

---

## Dependencies & Execution Order

### Phase Dependencies

1. **Phase 1 (Setup)**: Blocks everything.
2. **Phase 2 (Math Engine)**: Blocks Phase 3 (Cognitive Layer).
3. **Phase 3 (Agents)**: Blocks Phase 4 (Monitoring/Approval).
4. **Phase 4 (Monitor/XAI)**: Finalizes the user-facing loop.

### User Story Mapping

- **US1 (Shadow Trading)**: T014, T015
- **US2 (Automated Monitoring)**: T006, T007, T008
- **US3 (Adversarial Validation)**: T011, T012, T013, T017
- **US4 (High-Value Approval)**: T016, T019, T020

### Parallel Opportunities

- T003, T004, T005 can run in parallel.
- T006, T007, T009 can run in parallel within Phase 2.
- T011, T012 can run in parallel within Phase 3.
- T018, T020 can run in parallel within Phase 4.

---

## Implementation Strategy

### MVP First (User Stories 1 & 2)

1. Complete Phase 1 & 2.
2. Implement US2 (Monitoring) and US1 (Shadow Mode).
3. **VALIDATE**: Verify the bot detects signals and "trades" them in the virtual ledger without AI debate.

### Full Agentic Cycle

1. Complete Phase 3 (LangGraph debate).
2. **VALIDATE**: Verify signals are filtered by Bull/Bear/News agents before reaching the shadow ledger.

### Secure Operations

1. Complete Phase 4 (Telegram & Risk Thresholds).
2. **VALIDATE**: Verify trades > $100 require manual approval and reports are generated.
