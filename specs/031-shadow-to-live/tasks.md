# Tasks: Shadow-to-Live Transition

**Feature Branch**: `031-shadow-to-live` | **Date**: 2026-04-07 | **Spec**: [specs/031-shadow-to-live/spec.md]

## Phase 1: Global Configuration & Setup
- [X] T001 [P] Add `LIVE_CAPITAL_DANGER: bool = Field(default=False)` to `src/config.py`
- [X] T002 Add `LIVE_CAPITAL_DANGER` to `execution-engine/src/main/java/com/arbitrage/engine/config/EnvironmentConfig.java`
- [X] T003 [P] Verify `pip install pytz` is in `requirements.txt` for timezone-aware worker logic

## Phase 2: Startup Safety Guards (Foundation)
- [X] T004 Implement Redis L2 entropy baseline check in `src/monitor.py`. Refuse boot if `LIVE_CAPITAL_DANGER=True` and baselines are missing.
- [X] T005 Implement Redis L2 entropy baseline check in `execution-engine/src/main/java/com/arbitrage/engine/Application.java`.
- [X] T006 [P] Add unit test `tests/unit/test_startup_guards.py` to verify boot refusal on missing baselines.

## Phase 3: Core Java - Kill Switch & Liquidation
- [X] T007 Define `KillSwitch` RPC in `execution-engine/src/main/proto/execution.proto`
- [X] T008 Implement `TriggerKillSwitch` in `ExecutionServiceImpl.java` using an `AtomicBoolean` state.
- [X] T009 Add `cancelAllOrders()` and `liquidateAllPositions()` to the `Broker` interface and `LiveBroker` implementation.
- [X] T010 Hook `killSwitch` state into the `executeTrade` flow to block new signals and trigger liquidation.

## Phase 4: Core Python - Telemetry & Daemon Hardening
- [X] T011 Update `src/services/telemetry_service.py` to use `asyncio.Queue(maxsize=10000)` with `put_nowait()` and `QueueFull` handling.
- [X] T012 Update `src/daemons/sec_fundamental_worker.py` to enforce the 04:00-09:15 EST execution window.
- [X] T013 Implement "Hard Kill" logic in `sec_fundamental_worker.py` to exit at exactly 09:15 EST.

## Phase 5: Frontend - Situational Awareness & Stability
- [X] T014 [P] Update `frontend/src/components/PixelBot.tsx` to sync with Risk HUD telemetry (Entropy > 0.8 -> GLITCH).
- [X] T015 Enforce 100-entry strict ring-buffer in `frontend/src/components/ThoughtJournal.tsx`.
- [X] T016 Verify frontend memory stability under a simulated 5,000 msg/sec telemetry burst.

## Phase 6: Integration & Final Audit
- [X] T017 Implement integration test `tests/integration/test_kill_switch_liquidation.py` to verify end-to-end emergency halt.
- [X] T018 Final audit: Verify transition requires zero code changes (only ENV vars).

## Dependency Graph
1. **Setup** (T001-T003) -> **Foundation** (T004-T006)
2. **Foundation** -> **Core Java** (T007-T010) & **Core Python** (T011-T013)
3. **Core Python** -> **Frontend** (T014-T016)
4. **All Core** -> **Integration** (T017-T018)
