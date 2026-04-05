# Tasks: Investor Suite Architectural Enforcement

**Input**: Design documents from `/specs/016-investor-suite-enforcement/`
**Prerequisites**: plan.md, spec.md

**Organization**: Tasks are grouped by priority levels (P0, P1, P2) as requested, while maintaining traceability to User Stories (US1-US4) from the specification.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1: Arbitrage, US2: Execution Safety, US3: Stability, US4: Hedging Compliance
- Exact file paths and methods included in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and environment verification

- [X] T001 Verify project structure and branch `016-investor-suite-enforcement`
- [ ] T002 [P] Verify mandatory API keys (T212, Data Service) via `speckit.verify-env`
- [ ] T003 [P] Configure `pytest` for new architectural regression tests

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data availability for architectural fixes

- [X] T004 [P] Ensure `data_service.get_latest_price` is fully functional for fallbacks in `src/services/data_service.py`
- [ ] T005 [P] Expose instrument metadata (`minTradeQuantity`, `quantityIncrement`) in `src/services/brokerage_service.py`
- [ ] T006 [P] Define `calculate_friction` method in `src/services/risk_service.py` to replace/alias `FeeAnalyzer.check_fees`

---

## Phase 3: P0 (Critical) - Math & Safety 🎯 MVP

**Goal**: Fix Statistical Arbitrage OLS regression and prevent $0.00 commitment loops.

**Independent Test**: Verify OLS includes intercept; verify pending orders use fallback price when broker returns $0.00.

### Tests for P0 (Critical)

- [X] T007 [P] [US1] Unit test for OLS regression with/without intercept in `tests/unit/test_arbitrage_math.py`
- [X] T008 [P] [US2] Integration test for $0.00 commitment fallback in `tests/integration/test_brokerage_safety.py`

### Implementation for P0

- [X] T009 [US1] Update `ArbitrageService.check_cointegration` to use `sm.add_constant(s2)` for OLS in `src/services/arbitrage_service.py`
- [X] T010 [US2] Update `BrokerageService.get_pending_orders_value` to use `data_service.get_latest_price` if `price == 0` for any order in `src/services/brokerage_service.py`

---

## Phase 4: P1 (High) - Limits & Friction

**Goal**: Enforce T212 execution limits and normalize friction math.

**Independent Test**: Verify value orders are rounded to broker increments; verify flat spread inputs are correctly converted to percentage.

### Tests for P1 (High)

- [ ] T011 [P] [US2] Unit test for quantity increment rounding in `tests/unit/test_brokerage_limits.py`
- [ ] T012 [P] [US2] Unit test for friction percentage conversion in `tests/unit/test_risk_math.py`

### Implementation for P1

- [ ] T013 [US2] Update `BrokerageService.place_value_order` to validate quantity against `minTradeQuantity` and `quantityIncrement` from `get_symbol_metadata()` in `src/services/brokerage_service.py`
- [X] T014 [US2] Implement logic in `RiskService.calculate_friction` to convert flat spread inputs to percentage based on current price before comparison in `src/services/risk_service.py`

---

## Phase 5: P2 (Medium) - Stability & Compliance

**Goal**: Enhance multi-agent resilience and ensure EU UCITS compliance for hedging.

**Independent Test**: Verify orchestrator survives agent exceptions; verify EU region selects UCITS inverse ETFs.

### Tests for P2 (Medium)

- [X] T015 [P] [US3] Simulation test for agent crash in `tests/integration/test_orchestrator_resilience.py`
- [X] T016 [P] [US4] Region-aware hedging test in `tests/unit/test_hedging_compliance.py`

### Implementation for P2

- [X] T017 [US3] Update `Orchestrator.ainvoke` to use `return_exceptions=True` in `asyncio.gather` calls for agents in `src/agents/orchestrator.py`
- [X] T018 [US4] Update `RiskService.check_hedging` to include a regional lookup for UCITS fallbacks (e.g., EU-equivalent inverse ETFs) in `src/services/risk_service.py`

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and final health checks

- [ ] T019 [P] Update `docs/agents.md` to reflect new stability and compliance architecture
- [ ] T020 [P] Run `/dev.audit` to ensure all architectural rules are enforced and no regressions exist
- [X] T021 Code cleanup and final type hint verification across updated services

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup & Foundational (Phases 1-2)**: Prerequisite for all implementation tasks.
- **P0 Implementation (Phase 3)**: Critical path - MUST be completed first.
- **P1 & P2 Implementation (Phases 4-5)**: Can proceed in parallel after P0 is verified.
- **Polish (Phase 6)**: Final sign-off.

### Parallel Opportunities

- T004, T005, T006 can run in parallel.
- All unit/integration tests within a phase can run in parallel.
- Once P0 is complete, P1 and P2 can be worked on simultaneously by different developers.

---

## Implementation Strategy

### MVP First (P0 Only)

1. Complete Setup and Foundational data exposure.
2. Implement US1 Intercept and US2 Commitment Fallback.
3. **VALIDATE**: Run P0 tests to confirm core safety and math integrity.

### Incremental Delivery

1. Deploy P0 (Safety & Core Math).
2. Follow with P1 (Execution Precision & Risk Validation).
3. Finalize with P2 (Stability & Regional Compliance).

---

## Notes

- **Friction Math**: Ensure `calculate_friction` correctly handles the case where `data_service` might be offline (use reasonable default or fail safe).
- **T212 Metadata**: Cache metadata locally for the duration of the session to avoid excessive API calls to `/instruments`.
- **Orchestrator**: Ensure that if `return_exceptions=True` is used, the aggregation logic correctly filters out `Exception` objects from the results list.
