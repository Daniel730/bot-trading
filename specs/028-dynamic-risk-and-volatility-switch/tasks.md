# Tasks: Dynamic Risk and Volatility Switch

**Feature Branch**: `028-dynamic-risk-and-volatility-switch`  
**Created**: 2026-04-06  
**Status**: Draft  
**Plan**: [specs/028-dynamic-risk-and-volatility-switch/plan.md]

## Phase 1: Performance Tracking (Internal Risk)

- [ ] T001 [P] Create `portfolio_performance` table in PostgreSQL migration script in `execution-engine/src/main/resources/db/migration/V2__Add_Portfolio_Stats.sql`
- [ ] T002 Implement `PerformanceService` to calculate rolling Sharpe and Max Drawdown in `src/services/performance_service.py`
- [ ] T003 Update `RiskService` to apply performance-based scaling to Kelly sizing in `src/services/risk_service.py`
- [ ] T004 Unit test for `PerformanceService` ensuring correct drawdown calculation in `tests/unit/test_performance_service.py`

## Phase 2: Volatility Switch (External Risk)

- [ ] T005 [P] Implement Shannon Entropy calculation for L2 snapshots in `src/services/volatility_service.py`
- [ ] T006 Create Redis pusher for entropy status updates in `src/services/volatility_service.py`
- [ ] T007 Integration test using `DEV_MODE` crypto data to baseline entropy signatures in `tests/integration/test_volatility_switch.py`

## Phase 3: gRPC & Execution Gate

- [ ] T008 Update `ExecutionServiceClient` to fetch real-time `max_slippage` from `VolatilityService` in `src/services/execution_service_client.py`
- [ ] T009 Update `mcp_server.py` to expose volatility status as an informational tool.
- [ ] T010 End-to-end test: Verify gRPC request contains tightened slippage during a simulated volatility spike in `tests/integration/test_dynamic_slippage.py`

## Phase 4: Polish & Documentation

- [ ] T011 Document the Entropy formula and baselining process in `specs/028-dynamic-risk-and-volatility-switch/research.md`
- [ ] T012 Finalize `quickstart.md` for feature 028.
