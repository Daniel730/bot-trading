# Tasks: Strategic Arbitrage Engine

**Input**: Design documents from `/specs/003-strategic-arbitrage-engine/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included for statistical math, brokerage integration, and rebalance logic.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create project structure: `src/models/`, `src/services/`, `scripts/`, `tests/unit/`, `tests/integration/`
- [X] T002 [P] Create `.env.template` and implement `src/config.py` for environment management
- [X] T003 Initialize Python 3.11 environment and install dependencies: `fastmcp`, `yfinance`, `polygon-api-client`, `statsmodels`, `pandas`, `python-telegram-bot`, `tenacity`, `quantstats`, `holidays`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Create SQLite schema initialization script in `scripts/init_db.py` (Pairs, Signals, Pie, Ledger)
- [X] T005 Implement Pydantic DataModels in `src/models/arbitrage_models.py` per data-model.md
- [X] T006 [P] Implement `BrokerageService` in `src/services/brokerage_service.py` with Basic Auth and market order stubs
- [X] T007 [P] Implement `DataService` in `src/services/data_service.py` with yfinance history and Polygon.io WebSocket client
- [X] T008 [P] Implement `NotificationService` in `src/services/notification_service.py` with async Telegram bot and approval buttons
- [X] T009 Implement OLS (Ordinary Least Squares) engine for hedge ratio and spread calculation in `src/services/arbitrage_service.py`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Statistical Monitoring (Priority: P1) 🎯 MVP

**Goal**: Continuous monitoring of cointegrated pairs and Z-Score signal generation

**Independent Test**: Provide historical data for a pair and verify Z-Score calculations for 30/60/90 windows against reference values

### Tests for User Story 1

- [X] T010 [P] [US1] Write unit tests for Z-Score and OLS math in `tests/unit/test_arbitrage.py`

### Implementation for User Story 1

- [X] T011 [US1] Implement multi-window Z-Score (30, 60, 90) logic in `src/services/arbitrage_service.py`
- [X] T012 [US1] Implement core monitoring loop in `src/monitor.py` utilizing `DataService` WebSockets
- [X] T013 [US1] Implement entry/exit signal generation logic ($|Z| > 2.5$ / $|Z| < 0.5$) and SQLite persistence in `src/monitor.py`

**Checkpoint**: US1 is functional - bot detects statistical anomalies and records signals

---

## Phase 4: User Story 2 - Fundamental Validation via AI (Priority: P1)

**Goal**: Validate statistical signals using Gemini CLI and news analysis

**Independent Test**: Trigger a signal, verify `analyze_news` tool is called, and AI decision is recorded in SQLite

### Implementation for User Story 2

- [X] T014 [P] [US2] Create FastMCP server in `src/mcp_server.py`
- [X] T015 [US2] Implement `analyze_news` (sentiment/filings) and `assess_risk` tools in `src/mcp_server.py`
- [X] T016 [US2] Integrate Gemini CLI validation loop into `src/monitor.py` using `SignalRecord` status
- [X] T017 [US2] Implement detailed decision logging in `src/monitor.py` for AI auditing per user input

**Checkpoint**: US2 is functional - signals are now validated by AI before execution

---

## Phase 5: User Story 3 - "Virtual Pie" Execution (Priority: P2)

**Goal**: Execute risk-aware rebalancing on Trading 212 via individual orders

**Independent Test**: Approve a trade via Telegram and verify correct market orders (quantity) are sent and SQLite state updated

### Tests for User Story 3

- [X] T018 [P] [US3] Integration test for market order execution (Basic Auth) in `tests/integration/test_brokerage.py` (Mock API)

### Implementation for User Story 3

- [X] T019 [US3] Implement Atomic rebalance logic (Sell-then-Buy) in `src/services/arbitrage_service.py`
- [X] T020 [US3] Implement `place_market_order` and `fetch_positions` in `src/services/brokerage_service.py` per contracts.md
- [X] T021 [US3] Implement Virtual Pie state reconciliation and startup re-sync in `src/monitor.py`

**Checkpoint**: US3 is functional - bot rebalances real or virtual positions upon confirmation

---

## Phase 6: User Story 4 - Paper Trading (Priority: P1)

**Goal**: Validate strategy using live data without committing real capital

**Independent Test**: Set `PAPER_TRADING=true`, trigger a trade, and verify it appears in `Simulated Ledger` but not on brokerage

### Implementation for User Story 4

- [ ] T022 [US4] Implement simulated ledger tracking and virtual balance logic in `src/services/arbitrage_service.py`
- [ ] T023 [US4] Implement conditional execution logic (Live vs Paper) in `src/monitor.py` based on `.env`

**Checkpoint**: US4 is functional - strategy can be validated in a risk-free environment

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Operating hours, performance reports, and final hardening

- [X] T024 [P] Implement NYSE operating hours and holiday check (using `holidays` lib) in `src/services/data_service.py`
- [ ] T025 [P] Implement Sharpe Ratio and Drawdown calculation reports using `quantstats` in `src/services/notification_service.py`
- [ ] T026 Implement headless deployment orchestrator and exception handling for `EquityNotOwned` in `src/monitor.py`
- [ ] T027 Run final validation of `quickstart.md` steps

---

## Dependencies & Execution Order

### Phase Dependencies

1. **Setup (Phase 1)**: Must complete first.
2. **Foundational (Phase 2)**: BLOCKS all user stories.
3. **User Story 1 (US1)**: Priority P1, depends on Phase 2.
4. **User Story 2 & 4 (US2, US4)**: Priority P1, depend on US1 completion.
5. **User Story 3 (US3)**: Priority P2, depends on US1/US2.
6. **Polish (Phase N)**: Final refinement.

### Independent Test Criteria

- **US1**: Z-Score calculation accuracy (30/60/90 windows) vs reference data.
- **US2**: AI "GO/NO-GO" decision successfully retrieved and logged for a mock signal.
- **US3**: Target allocation reached within 0.5% drift after simulated rebalance.
- **US4**: Zero brokerage API calls recorded when `PAPER_TRADING=true`.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Setup and Foundational phases.
2. Implement US1 Monitoring and OLS Math Engine.
3. **STOP and VALIDATE**: Verify Z-Score signals are generated correctly in the logs.

### Incremental Delivery
1. Add US4 (Paper Trading) to validate the full loop without financial risk.
2. Add US2 (AI Validation) to increase signal quality.
3. Add US3 (Live Execution) for actual trading.
4. Add Phase N for production readiness (Hours, Performance Reports).

---

## Parallel Opportunities
- T006, T007, T008 (Infrastructure services)
- T010 (Math tests) while building OLS Engine (T009)
- T014 (MCP Server) while building US1 logic
- T024 (Hours logic) can start any time after Setup
