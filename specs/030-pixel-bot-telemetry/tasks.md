# Tasks: Agent Thought Journal Dashboard with Pixel Bot

**Feature Branch**: `030-pixel-bot-telemetry` | **Date**: 2026-04-06 | **Spec**: [specs/030-pixel-bot-telemetry/spec.md]

## Phase 1: Setup
- [X] T001 [P] Verify `bot_spritesheet.png` contains frames for `IDLE`, `DOUBT`, `GLITCH`, `HAPPY` moods in `frontend/public/assets/`
- [X] T002 [P] Install `vitest` and `@testing-library/react` for frontend unit testing in `frontend/package.json`

## Phase 2: Foundational Backend Telemetry
- [X] T003 Implement `ConnectionManager` in `src/services/dashboard_service.py` to handle WebSocket client lifecycle and token validation
- [X] T004 Create `/ws/telemetry` WebSocket route in `src/services/dashboard_service.py`
- [X] T005 [P] Implement `asyncio.Queue` based broadcast logic in `src/services/telemetry_service.py`
- [X] T006 Implement background consumer task in `TelemetryService` to drain queue and send via `ConnectionManager`
- [X] T007 Implement fire-and-forget `broadcast(type, data)` producer in `src/services/telemetry_service.py`

## Phase 3: User Story 1 - Institutional HUD & Risk HUD [US1]
- [X] T008 [P] [US1] Hook `RiskService.get_execution_params` to broadcast `risk` events in `src/services/risk_service.py`
- [X] T009 [US1] Implement `useTelemetry` React hook in `frontend/src/hooks/useTelemetry.ts` to manage WebSocket connection and state
- [X] T010 [US1] Update `frontend/src/App.tsx` to display real-time Risk HUD (Multiplier, Drawdown, Entropy) using telemetry state
- [X] T011 [US1] Add hardware-accelerated transitions for HUD value updates in `frontend/src/App.css`

## Phase 4: User Story 2 - Pixel Bot Emotional State [US2]
- [X] T012 [P] [US2] Update `src/agents/orchestrator.py` to broadcast `bot_state` events based on aggregated agent verdicts
- [X] T013 [US2] Update `frontend/src/components/PixelBot.tsx` to support `DOUBT` and `GLITCH` moods with corresponding sprite offsets
- [X] T014 [US2] Implement mood resolution logic in `frontend/src/App.tsx` (Entropy > 0.8 -> GLITCH, etc.)
- [X] T015 [US2] Apply `will-change: transform` and `translate3d` to `PixelBot` container in `frontend/src/components/PixelBot.tsx`

## Phase 5: User Story 3 - Stable Thought Journal [US3]
- [X] T016 [P] [US3] Hook `Orchestrator` reasoning steps to broadcast `thought` events in `src/agents/orchestrator.py`
- [X] T017 [US3] Create `ThoughtJournal.tsx` component in `frontend/src/components/ThoughtJournal.tsx` with a strict 100-entry ring-buffer
- [X] T018 [US3] Integrate `ThoughtJournal` into `frontend/src/App.tsx` and verify memory stability under load
- [X] T019 [US3] Add unit test for ring-buffer logic in `frontend/src/components/ThoughtJournal.test.tsx`

## Phase 6: User Story 4 - Zero-Latency Telemetry [US4]
- [X] T020 [US4] Implement integration test `tests/integration/test_telemetry_hotpath.py` to measure gRPC latency under high telemetry load
- [X] T021 [US4] Verify background task exception handling in `TelemetryService` ensures trading loop continuity

## Phase 7: Polish & Cross-Cutting
- [X] T022 Implement WebSocket auto-reconnect with exponential backoff in `frontend/src/hooks/useTelemetry.ts`
- [X] T023 Add "Connection Status" visual indicator to the dashboard header in `frontend/src/App.tsx`
- [X] T024 Final audit of CSS hardware acceleration across all dynamic dashboard components

## Dependency Graph
1. **Foundational** (T003-T007) -> **US1** (T008-T011)
2. **Foundational** (T003-T007) -> **US2** (T012-T015)
3. **US1 & US2** -> **US3** (T016-T019)
4. **All Core** -> **US4** (T020-T021)
5. **All US** -> **Polish** (T022-T024)

## Implementation Strategy
- **Phase 2 & 3 (MVP)**: Get the WebSocket stream running and verify Risk HUD updates.
- **Phase 4 (Visuals)**: Map the emotional states to the Pixel Bot.
- **Phase 5 (Stability)**: Enforce the 100-entry ring-buffer to prevent browser crashes.
- **Phase 6 (Verification)**: Crucial performance benchmark before deployment.
