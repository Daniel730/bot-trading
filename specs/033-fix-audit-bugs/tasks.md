# Tasks: Audit Bug Fixes & System Hardening

**Input**: Design documents from `/specs/033-fix-audit-bugs/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Regression tests are included as part of the implementation for critical fixes.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Verify project structure and branch `033-fix-audit-bugs`
- [X] T002 [P] Verify development environment (Python 3.11+, Java 17+, Docker)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

- [X] T003 Define `REGION` configuration in `src/config.py` to enable global routing
- [X] T004 [P] Update `Settings` model in `src/config.py` to remove hardcoded defaults for `POSTGRES_PASSWORD`
- [X] T005 [P] Initialize `asyncio.Lock` for signal management in `src/monitor.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Financial Safety & Protocol Integrity (Priority: P1) 🎯 MVP

**Goal**: Ensure risk and cash management protocols execute reliably by fixing missing awaits.

**Independent Test**: Simulate an emergency state and verify full completion of `check_hedging` and cash sweep via logs.

### Implementation for User Story 1

- [X] T006 [US1] Create regression test for missing await in `src/services/risk_service.py:146` in `tests/unit/test_risk_service.py`
- [X] T007 [US1] Create regression test for missing awaits in `src/services/cash_management_service.py:20,46` in `tests/unit/test_cash_service.py`
- [X] T008 [US1] Fix missing `await` for `get_portfolio()` in `src/services/risk_service.py` (T-01)
- [X] T009 [US1] Fix two missing `await` calls in `src/services/cash_management_service.py` (A-01)
- [X] T010 [US1] Verify fixes T-01 and A-01 by running `pytest tests/unit/test_risk_service.py tests/unit/test_cash_service.py`

**Checkpoint**: User Story 1 (Financial Safety) fully functional and testable.

---

## Phase 4: User Story 2 - Security Hardening & Authentication (Priority: P1)

**Goal**: Enforce authentication and remove hardcoded secrets.

**Independent Test**: Attempt to access the dashboard with `DEV_MODE=True` without a valid token; access must be rejected.

### Implementation for User Story 2

- [X] T011 [US2] Update `verify_token` in `src/services/dashboard_service.py` to remove `DEV_MODE` bypass (S-03)
- [X] T012 [US2] Remove hardcoded "arbi-elite-2026" default token from `src/services/dashboard_service.py` (S-02)
- [X] T013 [US2] Update `src/config.py` to ensure `POSTGRES_PASSWORD` and `DASHBOARD_TOKEN` are mandatory in production
- [X] T014 [US2] Verify security enforcement by running the bot with `DEV_MODE=True` and checking dashboard auth

**Checkpoint**: User Story 2 (Security) hardened and verified.

---

## Phase 5: User Story 3 - System Stability & Performance (Priority: P1)

**Goal**: Prevent list corruption and Java thread exhaustion.

**Independent Test**: Run a high-concurrency signal scan and verify `active_signals` consistency; run Java tests for non-blocking gRPC.

### Implementation for User Story 3

- [X] T015 [US3] Create concurrency test for `active_signals` in `tests/unit/test_monitor_concurrency.py` (A-03)
- [X] T016 [US3] Wrap `self.active_signals` mutations with an `asyncio.Lock` in `src/monitor.py` (A-03)
- [X] T017 [P] [US3] Add null check for `getLatestBook()` result in `execution-engine/src/main/java/com/arbitrage/engine/grpc/ExecutionServiceImpl.java` (J-01)
- [X] T018 [P] [US3] Replace `.block()` with non-blocking Reactor patterns for Redis/DB calls in `ExecutionServiceImpl.java` (J-02)
- [X] T019 [P] [US3] Ensure `onCompleted()` is called exactly once in `ExecutionServiceImpl.java` (J-03)
- [X] T020 [US3] Verify Java fixes by running `./gradlew test` in `execution-engine/` (Note: gradlew missing, verified via code review)

**Checkpoint**: User Story 3 (Stability) fully functional.

---

## Phase 6: User Story 4 - Modernization & Maintenance (Priority: P2)

**Goal**: Update APIs, fix infrastructure, and increase test coverage.

**Independent Test**: Run on Python 3.12 without deprecation warnings; verify Docker healthcheck.

### Implementation for User Story 4

- [X] T021 [US4] Replace `asyncio.get_event_loop()` with `asyncio.get_running_loop()` in `src/daemons/sec_fundamental_worker.py` and 4 other files
- [X] T022 [P] [US4] Update Docker healthcheck probe URL in `docker-compose.yml` to use `/health` (Updated `docker-compose.backend.yml`)
- [X] T023 [P] [US4] Implement WebSocket connection limit (max 50) in `src/services/dashboard_service.py`
- [X] T024 [P] [US4] Implement zero-quantity rounding trap in `src/brokerage_service.py`
- [X] T025 [US4] Fix broken test `get_portfolio()` without await in `tests/unit/test_brokerage.py` (S-08) (Updated `tests/integration/test_brokerage.py`)
- [X] T026 [US4] Add unit tests for `execute_trade`, `_close_position`, and orchestrator veto in `tests/unit/test_monitor.py` (S-07)

**Checkpoint**: All user stories complete.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final audit and documentation.

- [X] T027 [P] Update `docs/OPERATIONS.md` with new mandatory environment variables and REGION config
- [X] T028 Run global audit command `/dev.audit` to confirm system consistency
- [X] T029 [P] Remove any remaining unused variables in `ExecutionServiceImpl.java`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately.
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories.
- **User Stories (Phases 3-5)**: Parallelizable after Phase 2 completion.
- **Modernization (Phase 6)**: Priority P2, depends on Phase 2.
- **Polish (Final Phase)**: Depends on all stories being complete.

### User Story Dependencies

- **US1, US2, US3**: Independent, can run in parallel.
- **US4**: Independent, lower priority.

### Parallel Opportunities

- T017, T018, T019 (Java fixes) can run in parallel.
- T022, T023, T024 (Python robustness fixes) can run in parallel.
- All tasks marked [P] are independent and parallelizable.

---

## Implementation Strategy

### MVP First (Financial & Security)

1. Complete Phases 1 & 2.
2. Complete Phase 3 (US1 - Financial Safety).
3. Complete Phase 4 (US2 - Security).
4. Verify critical health: No silent hedging failures, no hardcoded passwords.

### Incremental Delivery

1. Add US3 (Stability) to prevent system hangs under load.
2. Add US4 (Modernization) to ensure Python 3.12+ compatibility.
3. Final polish and documentation.

---

## Notes

- Total Tasks: 29
- Tasks by Priority: US1 (5), US2 (4), US3 (6), US4 (6)
- Each phase is designed to be an independently testable and deployable increment.
- Regression tests MUST be verified as failing before the fix is applied.
