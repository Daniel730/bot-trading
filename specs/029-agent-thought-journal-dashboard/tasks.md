# Tasks: Agent Thought Journal Dashboard

**Feature Branch**: `029-agent-thought-journal-dashboard` | **Date**: 2026-04-06 | **Spec**: [specs/029-agent-thought-journal-dashboard/spec.md]

## Phase 1: Setup & Foundational Infrastructure
- [x] T001 [P] Create `specs/029-agent-thought-journal-dashboard/contracts/telemetry.json` with JSON schema.
- [x] T002 [P] Configure `fastapi`/`uvicorn` for WebSockets.
- [x] T003 Implement `ConnectionManager` in `src/services/dashboard_service.py`.
- [x] T004 Create `/ws/telemetry` endpoint in `src/services/dashboard_service.py`.
- [x] T005 [P] Update `TelemetryService` with `asyncio.Queue`.
- [x] T006 Implement background broadcast task.
- [x] T007 Implement `broadcast(type, data)` producer.

## Phase 2: Backend Risk & Agent Hooks
- [x] T008 [P] Hook `RiskService.get_execution_params` to broadcast risk metrics.
- [x] T009 [P] Hook `Orchestrator` to broadcast agent reasoning.
- [ ] T010 Implement `CalibrationService` hook to broadcast achievability/uncertainty for "DOUBT" state.
- [ ] T011 Implement `VolatilityService` hook to broadcast entropy spikes for "GLITCH" state.

## Phase 3: React Frontend Integration [US1 & US2]
- [ ] T012 Update `frontend/src/services/api.ts` to support WebSocket `useTelemetry` hook.
- [ ] T013 Update `frontend/src/App.tsx` to handle `type: "risk"` and update the HUD.
- [ ] T014 Implement `ThoughtJournal.tsx` with a strict 100-entry ring-buffer.
- [ ] T015 Integrate `ThoughtJournal.tsx` into `frontend/src/App.tsx`.

## Phase 4: Pixel Bot "Institutional Awareness" [US2]
- [ ] T016 Update `PixelBot.tsx` to include `DOUBT` and `GLITCH` frames.
- [ ] T017 Implement mood mapping logic in `App.tsx` (Entropy -> GLITCH, Achievability -> DOUBT).
- [ ] T018 Apply hardware-accelerated CSS (`translate3d`, `will-change`) to the Pixel Bot container.

## Phase 5: Zero-Latency & Stability Verification [US3]
- [x] T019 [US3] Verify fire-and-forget producer latency via `tests/integration/test_telemetry_latency.py`.
- [ ] T020 [US3] Profile React frontend under 1000 msg/sec load to verify ring-buffer memory stability.
- [ ] T021 [US3] Ensure all animations are offloaded to the GPU.

## Phase 6: Polish
- [ ] T022 Add connection status indicator to React dashboard.
- [ ] T023 Synchronize Pixel Bot expressions with "Arbi Aura" glow colors.
