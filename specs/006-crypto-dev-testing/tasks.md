# Tasks: 24/7 Crypto Development Mode

**Input**: Design documents from `/specs/006-crypto-dev-testing/`
**Prerequisites**: plan.md (required), spec.md (required)

**Organization**: Tasks are grouped by phases to enable 24/7 testing of the arbitrage engine.

## Phase 1: Setup (Configuration)

**Purpose**: Define the development toggle and crypto test pairs.

- [X] T001 Add `DEV_MODE: bool = False` to `Settings` class in `src/config.py`
- [X] T002 Add `CRYPTO_TEST_PAIRS` list (BTC-USD, ETH-USD) to `src/config.py`
- [X] T003 Update `.env.template` to include `DEV_MODE=false`

---

## Phase 2: Foundational (Logic Bypass)

**Purpose**: Implement the hour bypass and dynamic pair selection.

- [X] T004 Modify `ArbitrageMonitor.run` in `src/monitor.py` to skip NYSE/NASDAQ hour checks if `settings.DEV_MODE` is True
- [X] T005 Update `ArbitrageMonitor.initialize_pairs` in `src/monitor.py` to use `CRYPTO_TEST_PAIRS` when `DEV_MODE` is active
- [X] T006 Ensure `DataService.get_historical_data` in `src/services/data_service.py` handles crypto ticker formats correctly (already supported, but verify)

---

## Phase 3: User Story 1 - 24/7 Connectivity Test (Priority: P1)

**Goal**: Validate the bot operates during weekends using crypto data.

**Independent Test**: Set `DEV_MODE=true` in `.env` and run the bot during a weekend to confirm initialization and signal detection.

- [X] T007 [US1] Run manual validation: Initialize bot with `DEV_MODE=true` and verify BTC-USD data fetch
- [X] T008 [US1] Verify signal generation (Z-score) for crypto pairs in `src/monitor.py`
- [X] T009 [US1] Confirm LangGraph adversarial debate processes crypto signal context in `src/agents/orchestrator.py`

---

## Phase N: Polish & Cross-Cutting Concerns

- [X] T010 Add logging warning in `src/monitor.py` when `DEV_MODE` is active to prevent accidental production use
- [X] T011 Documentation: Update README with dev mode instructions

---

## Dependencies & Execution Order

### Phase Dependencies

1. **Phase 1**: Setup variables.
2. **Phase 2**: Implement logic changes.
3. **Phase 3**: Execution and validation.

### Implementation Strategy

1. Enable `DEV_MODE` in config.
2. Inject crypto pairs into monitor.
3. Verify full agentic cycle (Data -> Monitor -> Agent -> Shadow Trade) works 24/7.
