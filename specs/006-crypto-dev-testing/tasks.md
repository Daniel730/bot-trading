---

description: "Actionable, dependency-ordered tasks for 24/7 Crypto Development Mode"
---

# Tasks: 24/7 Crypto Development Mode

**Input**: Design documents from `/specs/006-crypto-dev-testing/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md

**Tests**: Included for logic bypass and connectivity validation.

**Organization**: Tasks are grouped by logical phases to enable independent implementation and testing of the 24/7 monitoring capability.

## Phase 1: Setup (Configuration)

**Purpose**: Define the development toggle and test pairs in the settings layer.

- [X] T001 Add `DEV_MODE: bool = False` to the `Settings` class in `src/config.py`
- [X] T002 [P] Add `CRYPTO_TEST_PAIRS` (e.g., BTC-USD/ETH-USD) and `DEV_EXECUTION_TICKERS` (e.g., AAPL, MSFT) to `src/config.py`
- [X] T003 Update `.env.template` to include `DEV_MODE=false` as a documented environment variable

---

## Phase 2: Foundational (Logic Bypass)

**Purpose**: Implement the core infrastructure to ignore market hours and switch data sources.

**⚠️ CRITICAL**: This phase MUST be complete before the 24/7 testing story can be validated.

- [X] T004 Modify the `while True` loop in `src/monitor.py` to skip the NYSE/NASDAQ hour check if `settings.DEV_MODE` is True
- [X] T005 Update `ArbitrageMonitor.initialize_pairs` in `src/monitor.py` to load `CRYPTO_TEST_PAIRS` instead of production pairs when `DEV_MODE` is active
- [X] T006 [P] Ensure `DataService.get_historical_data` in `src/services/data_service.py` handles the `BTC-USD` ticker format and column suffixes correctly

**Checkpoint**: Foundation ready - the bot can now be started during weekends and will attempt to monitor crypto pairs.

---

## Phase 3: User Story 1 - 24/7 Connectivity Test (Priority: P1) 🎯 MVP

**Goal**: Validate that the bot maintains a stable data flow and completes the analysis cycle during off-hours.

**Independent Test**: Enable `DEV_MODE=true` on a weekend, verify crypto price updates in logs, and confirm agent debate triggers.

### Implementation for User Story 1

- [X] T007 [US1] Implement the 5-minute periodic `WARNING` log in `src/monitor.py` while `DEV_MODE` is active (FR-004)
- [X] T008 [US1] Update `ArbitrageMonitor` to use `DEV_EXECUTION_TICKERS` for order placement in `src/monitor.py` when `DEV_MODE` is True
- [X] T009 [US1] Implement a small-lot limit (e.g., 1.00 currency unit) for `DEV_MODE` execution in `src/monitor.py` to minimize risk
- [X] T010 [US1] Integrate `DataService` price fetching for crypto into the main loop in `src/monitor.py`

**Checkpoint**: User Story 1 is functional - the bot monitors 24/7 and can execute technical validation orders on stocks.

---

## Phase 4: Polish & Metrics (Observability)

**Purpose**: Implement connectivity tracking and performance logs (SC-001, SC-002).

- [X] T011 [P] Implement `total_cycles` and `successful_cycles` counters in `src/services/audit_service.py` to track connectivity (SC-001)
- [X] T012 [P] Add latency measurement for orchestrator responses in `src/monitor.py` and log if `< 10s` (SC-002)
- [X] T013 [P] Implement a "Connectivity: 100%" log summary in `src/monitor.py` calculated every 10 cycles
- [X] T014 Run final validation of all `quickstart.md` steps using `DEV_MODE=true`

---

## Dependencies & Execution Order

### Phase Dependencies

1. **Setup (Phase 1)**: Must complete first to provide the `DEV_MODE` flag.
2. **Foundational (Phase 2)**: Depends on Phase 1 - BLOCKS the monitoring logic.
3. **User Story 1 (Phase 3)**: Depends on Phase 2 - Implements the actual 24/7 flow.
4. **Polish (Phase 4)**: Final metrics and hardening.

### Implementation Strategy

1. **MVP First**: Complete Phase 1 and 2 to prove the bot can run on a Sunday.
2. **Connectivity**: Implement User Story 1 to see real crypto data flowing through the agents.
3. **Validation**: Use Phase 4 to verify the stability requirements (SC-001/SC-002) are met.

---

## Parallel Opportunities

- T002 (Config) can be done with T001.
- T006 (DataService) can be developed in parallel with the monitor bypass (T004).
- Metrics (T011, T012) can be implemented in parallel with the execution logic (T008, T009).
