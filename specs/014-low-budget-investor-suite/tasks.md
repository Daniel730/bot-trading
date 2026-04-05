# Tasks: Low-Budget Investor Suite & Portfolio Manager

**Input**: Design documents from `/specs/014-low-budget-investor-suite/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are included as requested in the feature specification for verification of fractional math, fee analysis, and DCA scheduling.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create feature directory structure in specs/014-low-budget-investor-suite/
- [X] T002 [P] Update src/config.py with new settings for `max_friction_pct` and `min_trade_value`
- [X] T003 [P] Update src/prompts.py with personas for `PortfolioManagerAgent` and `MacroEconomicAgent`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

- [X] T004 Update `init_db` in src/models/trading_models.py to include `portfolio_strategies`, `dca_schedules`, and `fee_config` tables
- [X] T005 [P] Implement `FeeConfiguration` model and persistence in src/models/trading_models.py
- [X] T006 [P] Implement `PortfolioStrategy` and `DCASchedule` models in src/models/trading_models.py
- [X] T007 Update `BrokerageService` in src/services/brokerage_service.py to support high-precision fractional quantities (6 decimal places)
- [X] T008 Implement base `FeeAnalyzer` logic in src/services/risk_service.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Micro-Budget Fractional Investing (Priority: P1) 🎯 MVP

**Goal**: Enable value-based fractional orders (e.g., "Buy $10 of AAPL") with strict fee-awareness.

**Independent Test**: Place a $10 order for a high-priced stock (e.g., TSLA) via the terminal and verify correct fractional quantity execution and fee rejection for sub-$1 trades.

### Tests for User Story 1

- [X] T009 [P] [US1] Unit test for fractional quantity calculation in tests/unit/test_fractional_math.py
- [X] T010 [P] [US1] Unit test for `FeeAnalyzer` rejection logic in tests/unit/test_fee_analyzer.py
- [X] T011 [US1] Integration test for value-based order flow in tests/integration/test_value_orders.py

### Implementation for User Story 1

- [X] T012 [US1] Implement `place_value_order` in src/services/brokerage_service.py (simulating value-based via quantity calculation)
- [X] T013 [US1] Integrate `FeeAnalyzer` into the trade execution flow in src/monitor.py to intercept high-friction trades
- [X] T014 [US1] Update Telegram Terminal handlers in src/services/notification_service.py to support `/invest [amount] of [ticker]`
- [X] T015 [US1] Add logging for fractional trade execution details in src/services/agent_log_service.py

**Checkpoint**: User Story 1 (MVP) functional: Value-based fractional trades with fee protection.

---

## Phase 4: User Story 2 - Automated DCA & Portfolio Management (Priority: P2)

**Goal**: Automate recurring micro-investments into predefined portfolio strategies.

**Independent Test**: Define a "safe" strategy, schedule a $1 DCA, and verify the `DCAService` triggers the `PortfolioManagerAgent` to allocate funds.

### Tests for User Story 2

- [X] T016 [P] [US2] Unit test for DCA scheduler logic in tests/unit/test_dca_scheduler.py
- [X] T017 [US2] Integration test for portfolio allocation in tests/integration/test_portfolio_orchestration.py

### Implementation for User Story 2

- [X] T018 [P] [US2] Create src/services/dca_service.py with background loop and market-hours check (Principle IV)
- [X] T019 [P] [US2] Create src/agents/portfolio_manager_agent.py to handle strategy-based allocation
- [X] T020 [US2] Implement `/portfolio define` and `/invest schedule` command handlers in src/services/notification_service.py
- [X] T021 [US2] Implement Dividend Reinvestment (DRIP) sweep logic in src/services/dca_service.py (depends on T018)
- [X] T022 [US2] Start `DCAService` background task in src/monitor.py

**Checkpoint**: User Story 2 functional: Automated wealth building via DCA and Portfolio Strategies.

---

## Phase 5: User Story 3 - Explainable Investment Thesis (Priority: P3)

**Goal**: Provide natural language justifications for trades and macro context.

**Independent Test**: Query `/why AAPL` after a trade and verify a multi-agent summary is returned.

### Tests for User Story 3

- [X] T023 [P] [US3] Unit test for Thesis generation prompt in tests/unit/test_thesis_prompt.py
- [X] T024 [P] [US3] Integration test for `/why` and `/macro` command responses in tests/integration/test_investor_persona.py
- [X] T024-A [P] [US3] Integration test for Macro Economic Agent data retrieval in tests/integration/test_macro_data.py

### Implementation for User Story 3

- [X] T025 [P] [US3] Create src/agents/macro_economic_agent.py for interest rate and market trend monitoring
- [X] T026 [US3] Implement `generate_investment_thesis` in src/agents/portfolio_manager_agent.py (querying audit logs)
- [X] T027 [US3] Add `/why` and `/macro` command handlers in src/services/notification_service.py
- [X] T028 [US3] Update `agent_log_service.py` to trigger thesis generation post-execution

**Checkpoint**: All user stories functional: Full Investor Persona with explainable AI.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final verification and documentation

- [X] T029 [P] Update README.md with new Investor Suite capabilities
- [X] T030 Perform full system dry-run with `DEV_MODE=true` for 24h cycle
- [X] T031 Refactor `monitor.py` to clean up new service initializations
- [X] T032 Validate all success criteria from spec.md using quickstart.md scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately.
- **Foundational (Phase 2)**: Depends on T001-T003. BLOCKS all user stories.
- **User Stories (Phase 3+)**: All depend on Phase 2. US2/US3 can run in parallel with US1 if models are ready.

### Parallel Opportunities

- T002, T003 (Setup)
- T005, T006, T007 (Foundational)
- All test tasks marked [P]
- T018, T019 (US2 Implementation)
- T025 (US3 Implementation)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Setup and Foundational.
2. Complete User Story 1 (Fractional value trades).
3. Validate SC-001 and SC-002.

### Incremental Delivery

1. Add User Story 2 (DCA) to automate the value trades.
2. Add User Story 3 (Advisor Persona) to explain the automated actions.
