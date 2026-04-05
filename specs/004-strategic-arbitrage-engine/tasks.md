---

description: "Execution tasks for Strategic Arbitrage Engine"
---

# Tasks: Strategic Arbitrage Engine

**Input**: Design documents from `/specs/004-strategic-arbitrage-engine/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included for core math engine and brokerage integration.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create project structure: `src/models/`, `src/services/`, `scripts/`, `tests/`
- [x] T002 [P] Configure environment management in `src/config.py` using `.env.template`
- [x] T003 Initialize Python 3.11 project and install dependencies: `fastmcp`, `pandas`, `statsmodels`, `python-telegram-bot`, `requests`, `yfinance`, `tenacity`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Create SQLite schema initialization script in `scripts/init_db.py` per data-model.md
- [x] T005 Implement Pydantic DataModels in `src/models/arbitrage_models.py`
- [x] T006 [P] Implement `BrokerageService` (T212 wrapper) in `src/services/brokerage_service.py`
- [x] T007 [P] Implement `DataService` (polling logic) in `src/services/data_service.py`
- [x] T008 [P] Implement `NotificationService` (Telegram async client) in `src/services/notification_service.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Statistical Monitoring (Priority: P1) 🎯 MVP

**Goal**: Continuous monitoring of cointegrated pairs and Z-Score signal generation

**Independent Test**: Provide historical data for a pair and verify Z-Score calculations for 30/60/90 windows match expected values.

### Implementation for User Story 1

- [x] T009 [US1] Implement OLS and Z-Score math engine in `src/services/arbitrage_service.py`
- [x] T010 [P] [US1] Write unit tests for arbitrage math in `tests/unit/test_arbitrage_math.py`
- [x] T011 [US1] Implement main orchestrator loop in `src/monitor.py`
- [x] T012 [US1] Implement signal generation and SQLite persistence in `src/monitor.py`

**Checkpoint**: US1 is functional - bot detects statistical anomalies and records signals

---

## Phase 4: User Story 4 - Paper Trading (Priority: P1)

**Goal**: Strategy validation using live data without committing real capital

**Independent Test**: Enable Paper Trading, trigger a trade, and verify it appears in `TradeLedger` but not on the brokerage.

### Implementation for User Story 4

- [x] T013 [US4] Implement simulated ledger tracking and virtual balance logic in `src/services/arbitrage_service.py`
- [x] T014 [US4] Implement conditional execution logic (Live vs Paper) in `src/monitor.py` based on `.env`

**Checkpoint**: US4 is functional - strategy can be validated in a risk-free environment

---

## Phase 5: User Story 2 - Fundamental Validation via AI (Priority: P1)

**Goal**: Validate statistical signals against news/filings using Gemini CLI

**Independent Test**: Trigger a signal, verify `analyze_news` is called, and AI rationale is persisted in SQLite.

### Implementation for User Story 2

- [x] T015 [P] [US2] Create FastMCP server with SSE transport in `src/mcp_server.py`
- [x] T016 [US2] Implement `analyze_news` and `record_ai_decision` tools in `src/mcp_server.py`
- [x] T017 [US2] Integrate Gemini CLI validation loop into `src/monitor.py` using `SignalRecord` status
- [x] T018 [US2] Implement AI decision logging and fallback logic for inconclusive data in `src/monitor.py`

**Checkpoint**: US2 is functional - signals are now fundamentally validated before user approval

---

## Phase 6: User Story 3 - "Virtual Pie" Execution (Priority: P2)

**Goal**: Execute atomic rebalancing trades upon human approval

**Independent Test**: Approve a trade via Telegram and verify correct market orders are sent to Trading 212.

### Implementation for User Story 3

- [x] T019 [US3] Implement interactive Telegram approval/rejection buttons in `src/services/notification_service.py`
- [x] T020 [US3] Implement rebalance quantity calculation logic in `src/services/arbitrage_service.py`
- [x] T021 [US3] Implement "Sell-then-Buy" execution sequence with liquidity safety check (abort swap if any leg is illiquid) and error recovery in `src/monitor.py`
- [x] T022 [P] [US3] Write integration tests for brokerage orders in `tests/integration/test_brokerage.py`

**Checkpoint**: US3 is functional - bot rebalances real positions upon confirmation

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T023 Implement NYSE operating hours (14:30-21:00 WET) guard in `src/monitor.py`
- [x] T024 Implement slippage tolerance check before order execution in `src/monitor.py`
- [x] T025 [P] Hardening: Add `ArbitrageError` exception hierarchy in `src/models/arbitrage_models.py`
- [X] T027 [SC] Verify SC-002 (AI Latency < 30s) and SC-004 (Portfolio Drift < 0.5%) using performance logs and simulation results
- [x] T026 Run final validation of all `quickstart.md` steps

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Must complete first.
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all User Stories.
- **US1 (Phase 3)**: P1 Priority - Foundation for all other stories.
- **US4 (Phase 4)**: P1 Priority - Can start after US1 core math.
- **US2 (Phase 5)**: P1 Priority - Can start after US1 monitoring loop.
- **US3 (Phase 6)**: P2 Priority - Depends on US1 and US2 completion.
- **Polish (Phase N)**: Final refinement.

### Parallel Opportunities

- Configuration (T002) can run with structure creation (T001).
- Foundational services (T006, T007, T008) can be built in parallel.
- Math engine tests (T010) while implementing engine (T009).
- FastMCP server (T015) while finishing US1 logic.

---

## Implementation Strategy

### MVP First (User Story 1 + 4)

1. Setup and Foundational layers.
2. Arbitrage math engine (OLS/Z-Score).
3. Monitoring loop with Paper Trading (No AI validation yet).
4. **VALIDATE**: See signals and virtual trades in SQLite.

### Full Delivery

1. Integrate Gemini CLI for fundamental validation (US2).
2. Implement Telegram Approval and T212 Live Execution (US3).
3. Apply safety guards (NYSE hours, slippage).
