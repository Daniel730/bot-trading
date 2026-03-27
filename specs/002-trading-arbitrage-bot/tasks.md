# Tasks: Trading Arbitrage Bot with Virtual Pie and AI Validation

**Input**: Design documents from `/specs/002-trading-arbitrage-bot/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included for core math and brokerage integration logic.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create project structure: src/models, src/services, tests/unit, tests/integration
- [X] T002 Configure virtual environment and install dependencies: `fastmcp`, `requests`, `yfinance`, `pytz`, `python-dotenv`, `statsmodels`, `pandas`
- [X] T003 Install Gemini CLI via npm and authenticate via Google Cloud
- [X] T004 Create `.env` template and `src/config.py` for environment management

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure for data, brokerage communication, and persistence

- [X] T005 [P] Create SQLite schema and initialization script in `src/models/trading_models.py` and `scripts/init_db.py`
- [X] T006 [P] Implement base `BrokerageService` in `src/services/brokerage_service.py` with Basic Auth and rate limiting
- [X] T007 [P] Implement `DataService` in `src/services/data_service.py` for Polygon.io Snapshot and yfinance fetching
- [X] T008 [P] Setup `NotificationService` for Telegram alerts with inline button support in `src/services/notification_service.py`
- [X] T009 Implement startup re-sync logic in `src/monitor.py` to fetch current quantities from `BrokerageService`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Real-time Signal Monitoring (Priority: P1) 🎯 MVP

**Goal**: Continuous monitoring of price spreads and Z-score calculation

**Independent Test**: Verify Z-score calculation accuracy with historical data

### Tests for User Story 1
- [X] T010 [P] [US1] Write unit tests for Z-score and ADF math in `tests/unit/test_arbitrage.py`

### Implementation for User Story 1
- [X] T011 [US1] [Math-Engine] Implement `ArbitrageService` in `src/services/arbitrage_service.py` with statsmodels integration
- [X] T012 [US1] [Logic-Controller] Implement core monitoring loop in `src/monitor.py` (refresh every 12-15 seconds per Polygon Free Tier)
- [X] T013 [US1] Integrate `DataService` with `ArbitrageService` to fetch and analyze real-time spreads

**Checkpoint**: US1 should detect signals and log them to SQLite independently

---

## Phase 4: User Story 2 - Contextual Validation & Oversight (Priority: P1)

**Goal**: AI-driven validation via Gemini CLI followed by manual user confirmation

**Independent Test**: Mock a news headline, verify AI "Go", and then verify Telegram confirmation request

### Implementation for User Story 2
- [X] T014 [P] [US2] Create `FastMCP` tool server in `src/mcp_server.py` exposing news, price tools, and confirmation triggers
- [X] T015 [US2] [Gemini-Context] Create system instruction prompt for "Financial Risk Analyst" in `src/prompts.py`
- [X] T016 [US2] Register MCP tools with Gemini CLI: `fastmcp install gemini-cli src/mcp_server.py`
- [X] T017 [US2] Implement validation hook in `src/monitor.py` to call Gemini CLI and then wait for user input via Telegram

**Checkpoint**: Signal detection now triggers an AI analysis followed by a manual confirmation request

---

## Phase 5: User Story 3 - "Virtual Pie" Execution (Priority: P2)

**Goal**: Risk-aware portfolio rebalancing and trade execution on T212

**Independent Test**: Simulate confirmed rebalance and check SQLite quantity updates and risk capping

### Tests for User Story 3
- [ ] T018 [P] [US3] Integration test for market order execution and balance fetching in `tests/integration/test_brokerage.py` (Mock API)

### Implementation for User Story 3
- [ ] T019 [US3] Implement `execute_market_order`, `get_positions`, and `get_cash_balance` in `src/services/brokerage_service.py`
- [ ] T020 [US3] Implement risk-capped rebalance logic (Principle II) in `src/services/arbitrage_service.py`
- [ ] T021 [US3] [Notify] Integrate Telegram success/failure alerts for final trade outcomes in `src/services/notification_service.py`

**Checkpoint**: Bot can now rebalance positions based on validated and manually confirmed signals

---

## Phase 6: User Story 4 - Market Hour Discipline (Priority: P1)

**Goal**: Enforce NYSE operating hours per Principle I

**Independent Test**: Verify bot sleep/wake logic based on WET vs NY time

### Implementation for User Story 4
- [ ] T022 [US4] Implement `pytz` timezone conversion and NYSE holiday check in `src/services/data_service.py`
- [ ] T023 [US4] Update `src/monitor.py` loop to sleep outside 14:30 - 21:00 WET window
- [ ] T024 [US4] Add "Market Open/Closed" status notifications to Telegram

**Checkpoint**: Bot is now constitutionally compliant regarding operating hours

---

## Phase N: Polish & Cross-Cutting Concerns

- [ ] T025 [P] Update `specs/002-trading-arbitrage-bot/quickstart.md` with final installation steps
- [ ] T026 Implement error retry logic for brokerage API timeouts and connection drops
- [ ] T027 Add performance logging to measure SC-002 (AI validation < 15s)

---

## Dependencies & Execution Order

1. **Setup (Phase 1)** -> Foundational (Phase 2)
2. **Foundational (Phase 2)** BLOCKS all US phases (includes critical Startup Sync).
3. **US1 (Monitoring)** must be complete before US2 and US3 can be fully integrated.
4. **US4 (Hours)** can be implemented in parallel with US1-US3 logic.
5. **Implementation Strategy**: Build MVP (Phase 1-3) first to prove signal detection.

## Parallel Opportunities
- T005, T006, T007 (Infrastructure services)
- T014 (MCP Server) while building Math Engine (T011)
- T018 (Execution tests) while building Monitoring logic (T012)
