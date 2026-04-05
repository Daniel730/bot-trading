# Tasks: Resolve Production Rigor Gaps

**Input**: Design documents from `/specs/017-resolve-production-gaps/`
**Prerequisites**: plan.md, spec.md, research.md

**Organization**: Tasks are grouped into logical implementation phases based on priority and dependencies.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable (independent file/logic)
- **[Story]**: US1: Price Resilience, US2: Circuit Breaker, US3: EU Compliance, US4: Friction, US5: OLS Math

---

## Phase 1: Setup & Foundations

- [X] T001 Verify project structure and branch `017-resolve-production-gaps`
- [X] T002 [P] Install `tenacity` dependency if missing in `requirements.txt`
- [X] T003 [P] Initialize `system_state` table in `src/models/persistence.py`

---

## Phase 2: Foundational Math & Resilience (MVP)

- [X] T004 [P] [US5] Implement `sm.add_constant()` fix in `src/services/arbitrage_service.py`
- [X] T005 [P] [US1] Apply `tenacity` retry decorator with 1s, 2s, 4s backoff to `DataService.get_latest_price` in `src/services/data_service.py`
- [X] T006 [US1] Add explicit price rejection logic (if both broker and data_service return 0.0) in `src/services/brokerage_service.py`

---

## Phase 3: Risk & Compliance

- [X] T007 [P] [US4] Implement strict micro-budget friction rejection ($5.00 limit, 1.5% max) in `RiskService.calculate_friction` in `src/services/risk_service.py`
- [X] T008 [P] [US3] Hardcode UCITS compliance dictionary (SPY, QQQ, IWM) in `src/services/risk_service.py`
- [X] T009 [US3] Add hedge bypass and CRITICAL alert logic for unmapped EU assets in `RiskService.check_hedging`

---

## Phase 4: System Safety (Circuit Breaker)

- [X] T010 [US2] Implement timeout tracking and status transition to `DEGRADED_MODE` in `Orchestrator.ainvoke` in `src/agents/orchestrator.py`
- [X] T011 [US2] Enforce `DEGRADED_MODE` entry blocks while allowing stops/maintenance in `src/agents/orchestrator.py`

---

## Phase 5: Verification & Polish

- [X] T012 [P] [US5] Unit test for OLS intercept in `tests/unit/test_arbitrage_math.py`
- [X] T013 [P] [US1] Integration test for exponential backoff in `tests/integration/test_data_resilience.py`
- [X] T014 [P] [US2] Simulation test for Circuit Breaker and `DEGRADED_MODE` in `tests/integration/test_circuit_breaker.py`
- [X] T015 Run final `/dev.audit` and cleanup type hints
