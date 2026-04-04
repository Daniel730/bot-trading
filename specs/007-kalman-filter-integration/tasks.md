---

description: "Dependency-ordered tasks for Kalman Filter Integration"
---

# Tasks: Kalman Filter Integration

**Input**: Design documents from `/specs/007-kalman-filter-integration/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md

**Organization**: Tasks follow the implementation of the math engine first, then persistence, and finally integration.

## Phase 1: Setup & Math Engine (Phase 1)

**Purpose**: Implementation of the recursive filter logic.

- [X] T001 Create `src/services/kalman_service.py` with the `KalmanFilter` class
- [X] T002 Implement the `predict()` and `update()` methods using `numpy` matrix math
- [X] T003 [P] Add unit tests in `tests/unit/test_kalman.py` to verify convergence on synthetic "drifting" data
- [X] T004 Implement a `calculate_spread_and_zscore` method that uses the current filter state and error variance

---

## Phase 2: State Persistence (Phase 2)

**Purpose**: Ensure the bot doesn't "forget" the learned hedge ratio on restart.

- [X] T005 [P] Create the `kalman_state` table in `src/models/persistence.py` or via `scripts/init_db.py`
- [X] T006 Implement `save_kalman_state` and `load_kalman_state` in `src/models/persistence.py`
- [X] T007 Handle JSON serialization/deserialization for the 2x2 covariance matrices (P, Q)

---

## Phase 3: Integration & Monitoring (Phase 3)

**Purpose**: Wire the Kalman Filter into the active monitoring loop.

- [X] T008 [US1] Update `ArbitrageService` in `src/services/arbitrage_service.py` to optionally use `KalmanFilter` instead of `OLS`
- [X] T009 [US1] Modify `ArbitrageMonitor.initialize_pairs` in `src/monitor.py` to seed new filters from OLS history if no persisted state exists
- [X] T010 [US1] Update the main loop in `src/monitor.py` to perform a Kalman update on every price tick
- [X] T011 [US2] Update `Signal` generation to use the Kalman-derived Z-score and log the `beta` to the `SignalRecord`

---

## Phase N: Polish & Configuration

- [X] T012 Add `KALMAN_DELTA` and `KALMAN_R` parameters to `src/config.py` for fine-tuning
- [X] T013 [P] Add an "Exploding Beta" guard in `kalman_service.py` to prevent runaway values during extreme volatility
- [X] T014 Update the `Thought Journal` log in `src/monitor.py` to include the current Kalman Gain and Beta

---

## Dependencies & Execution Order

1. **Setup (Phase 1)**: The math engine is the core prerequisite.
2. **Persistence (Phase 2)**: Necessary for restart stability.
3. **Integration (Phase 3)**: Connects the engine to the bot's live loop.

### Implementation Strategy

1. **Validate Math**: Run the synthetic tests (T003) to ensure the filter actually tracks a moving target.
2. **Seed and Run**: Seed the filter from existing OLS data to ensure an immediate "hot" start.
3. **Shadow Test**: Run in `Shadow Mode` first to observe the Kalman Z-score vs the old OLS Z-score in the logs.
