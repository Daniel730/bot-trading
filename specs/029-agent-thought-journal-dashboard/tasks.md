# Tasks: Agent Thought Journal Dashboard

**Feature Branch**: `029-agent-thought-journal-dashboard` | **Date**: 2026-04-06 | **Spec**: [specs/029-agent-thought-journal-dashboard/spec.md]

## Phase 1: Setup
- [x] T001 [P] Create `specs/029-agent-thought-journal-dashboard/contracts/telemetry.json` with the JSON schema for updates.
- [x] T002 [P] Ensure `fastapi` and `uvicorn` are correctly configured for WebSockets in `requirements.txt`.

## Phase 2: Foundational Telemetry Infrastructure
- [x] T003 Implement `ConnectionManager` class in `src/services/dashboard_service.py` to manage active WebSocket connections.
- [x] T004 Create `/ws/telemetry` WebSocket endpoint in `src/services/dashboard_service.py` with token authentication.
- [x] T005 [P] Update `TelemetryService` in `src/services/telemetry_service.py` to include an `asyncio.Queue` for buffering updates.
- [x] T006 Implement a background broadcast task in `TelemetryService` that drains the queue and sends to `ConnectionManager`.
- [x] T007 [P] Implement `TelemetryService.broadcast(payload: dict)` as a fire-and-forget producer using `queue.put_nowait()`.

## Phase 3: User Story 1 - Real-time Risk HUD [US1]
- [x] T008 [P] [US1] Update `src/services/risk_service.py` to broadcast risk parameters (`risk_multiplier`, `max_drawdown`, `volatility_status`) via `telemetry_service`.
- [x] T009 [US1] Add Risk HUD HTML placeholders in `dashboard/index.html` (Risk Multiplier, Drawdown %, Entropy).
- [x] T010 [US1] Update `dashboard/app.js` to initialize WebSocket connection to `/ws/telemetry`.
- [x] T011 [US1] Implement `updateRiskHUD(data)` in `dashboard/app.js` to handle `type: "risk"` telemetry updates.

## Phase 4: User Story 2 - Agent Thought Streaming [US2]
- [x] T012 [P] [US2] Update `src/agents/orchestrator.py` to broadcast its final verdict and reasoning via `telemetry_service`.
- [x] T013 [P] [US2] Update `src/agents/bull_agent.py` and `bear_agent.py` to broadcast their arguments via `telemetry_service`.
- [x] T014 [US2] Update `dashboard/app.js` to handle `type: "thought"` telemetry updates and prepend them to the `Thought Journal`.
- [x] T015 [US2] Refactor `addLog` in `dashboard/app.js` to support agent-specific styling and icons in the journal.

## Phase 5: User Story 3 - Zero-Latency Verification [US3]
- [x] T016 [US3] Create integration test `tests/integration/test_telemetry_latency.py` to measure gRPC execution time while streaming telemetry.
- [x] T017 [US3] Verify that a failed WebSocket broadcast (disconnected client) does not block the producer thread.

## Phase 6: Polish & Cross-cutting Concerns
- [x] T018 Implement client-side throttling in `dashboard/app.js` to prevent UI lag during high-frequency signal bursts.
- [x] T019 Add "Connection Status" indicator to the dashboard header to show WebSocket state.
- [x] T020 Final end-to-end audit: Ensure all agents (including SEC/Fundamental) are hooked into the telemetry stream.

## Dependency Graph
1. **Foundational** (T003-T007) -> **US1** (T008-T011)
2. **Foundational** (T003-T007) -> **US2** (T012-T015)
3. **US1 & US2** -> **US3** (T016-T017)
4. **All US** -> **Polish** (T018-T020)

## Parallel Execution Opportunities
- [P] T001 & T002 (Setup docs and requirements)
- [P] T005 & T007 (Telemetry service internal logic)
- [P] T008 (RiskService hooks) can be done in parallel with T009 (Dashboard HTML)
- [P] T012 & T013 (Agent hooks) are independent of frontend changes
