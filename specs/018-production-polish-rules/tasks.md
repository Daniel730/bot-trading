# Task List: Production-Grade Polish & Reliability Enforcement

**Feature Branch**: `018-production-polish-rules`  
**Created**: 2026-04-05  
**Status**: In Progress  

## Phase 0: Setup & Infrastructure

- [x] T001 [Setup] Verify `PersistenceManager` support for `kalman_state` and `system_state` tables.

## Phase 1: P0 - Critical Reliability (Core Implementation)

### API TTL Caching (P0)
- [x] T002 [Core] Implement a 5-second TTL cache in `src/services/brokerage_service.py` for `/portfolio` and `/orders`.
- [x] T003 [Test] Add integration test `tests/integration/test_brokerage_cache.py` to verify caching behavior and 429 prevention.

### Kalman Filter DB Persistence (P0)
- [x] T004 [Core] Update `ArbitrageService.get_or_create_filter` in `src/services/arbitrage_service.py` to reload persisted state.
- [x] T005 [Core] Ensure `ArbitrageMonitor` in `src/monitor.py` no longer handles persistence manually (delegate to service).
- [x] T006 [Test] Add integration test `tests/integration/test_kalman_persistence.py` to verify state survives restarts.

## Phase 2: P1 - Capital Protection (Core Implementation)

### Slippage Guards (P1)
- [x] T007 [Core] Implement 1% slippage guard (`limitPrice`) in `src/services/brokerage_service.py` for fractional market orders.
- [x] T008 [Test] Add unit test `tests/unit/test_slippage_guard.py` for buy and sell order price calculations.

### DRIP Tax Safety (P1)
- [x] T009 [Core] Implement `min(gross_dividend, available_free_cash)` safety cap in `src/services/brokerage_service.py`.
- [x] T010 [Test] Add unit test `tests/unit/test_drip_safety.py` to verify capital-aware reinvestment logic.

## Phase 3: P2 - Operation Sync (Polish)

### Timezone Refactor (P2)
- [x] T011 [Polish] Update `src/config.py` with NYSE regular hours (9:30 AM - 4:00 PM ET).
- [x] T012 [Polish] Refactor `src/monitor.py` to use `pytz` explicitly for 'America/New_York' synchronization.
- [x] T013 [Test] Verify market open/close logic during simulated DST transitions.

## Phase 4: Final Validation

- [x] T014 [Audit] Run a full project audit (`/dev.audit`) to ensure no patterns or principles are violated.
- [x] T015 [Polish] Update documentation to reflect the production-grade status of the Arbitrage Engine.

## Phase 5: Remediation of Audit Bugs (Lapidation)

### Quantitative & Mathematical (P0)
- [x] T016 [Core] Implement `NaN`/`Inf` covariance guard in `KalmanFilter.update`.
- [x] T017 [Core] Enforce `adjusted=True` in `DataService` historical queries.
- [x] T018 [Core] Eliminate look-ahead bias in `ArbitrageService.get_spread_metrics` using trailing windows.

### Execution & Brokerage (P0)
- [x] T019 [Core] Implement Idempotency Keys (UUIDs) in `BrokerageService.place_market_order`.
- [x] T020 [Core] Implement strict tick-size rounding for `limitPrice` in `BrokerageService`.
- [x] T021 [Core] Refactor position tracking to use execution reports rather than order requests.

### Agent Robustness (P1)
- [x] T022 [Core] Implement robust JSON regex extractor in `Agent` base class or prompt utility.
