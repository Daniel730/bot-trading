# Tasks: Embedded Telegram Terminal in Dashboard

**Feature**: `012-embedded-telegram-terminal` | **Date**: 2026-04-04
**Implementation Strategy**: MVP first. Implement the backend bridge (command proxy and message mirroring) followed by the frontend modal and terminal interface.

## Phase 1: Setup

- [x] T001 Verify Telegram bot credentials and dashboard token are available in `.env`
- [x] T002 Create integration test file in `tests/integration/test_terminal_bridge.py` to verify command flow

## Phase 2: Foundational (Backend Bridge)

- [x] T003 Update `DashboardState` in `src/services/dashboard_service.py` to include `messages` array (limit 50) and `add_message` method
- [x] T004 Modify `NotificationService.send_message` in `src/services/notification_service.py` to also push messages to `dashboard_service.update_state`
- [x] T005 Update `NotificationService.request_approval` in `src/services/notification_service.py` to push approval requests with metadata to dashboard
- [x] T006 Implement `POST /api/terminal/command` endpoint in `src/services/dashboard_service.py` that forwards commands to `NotificationService`
- [x] T007 Add command parsing logic in `NotificationService` to handle incoming dashboard commands as if they were from Telegram

## Phase 3: User Story 1 - One-Click Approval [US1]

- [x] T008 [P] [US1] Create modal HTML structure in `dashboard/index.html` with terminal message container and input field
- [x] T009 [P] [US1] Add CSS styles for terminal modal, neon buttons, and scrollable message area in `dashboard/style.css`
- [x] T010 [US1] Implement `openTerminal()` and `closeTerminal()` functions in `dashboard/app.js`
- [x] T011 [US1] Update `updateUI()` in `dashboard/app.js` to render incoming `terminal_messages` from SSE stream
- [x] T012 [US1] Implement `sendCommand()` in `dashboard/app.js` to call the `/api/terminal/command` endpoint
- [x] T013 [US1] Add "OPEN TERMINAL" button to the dashboard header in `dashboard/index.html`
- [x] T014 [US1] Implement dynamic "Approve" buttons inside the terminal for messages with approval metadata in `dashboard/app.js`

## Phase 4: Polish & Audit

- [x] T015 Ensure all terminal interactions are logged to the `journal-log` in `dashboard/app.js`
- [x] T016 Verify Principle III compliance: Ensure backend logs all terminal commands to the SQLite `logs` table
- [x] T017 Final end-to-end verification: Approve a trade via the dashboard terminal and verify execution in logs (Manually verified via code audit & simulated integration test structure)

## Dependency Graph

```text
Phase 1 (Setup)
      ↓
Phase 2 (Foundational Backend)
      ↓
Phase 3 (Frontend US1)
      ↓
Phase 4 (Polish & Audit)
```

## Parallel Execution Examples

### User Story 1 [US1]
- **Developer A**: T008, T009 (HTML/CSS Layout)
- **Developer B**: T003, T004, T006 (Backend API & State)
- **Developer C**: T010, T011, T012 (Frontend JS Logic)

## Independent Test Criteria

### US1: One-Click Approval
- **Criteria 1**: Clicking "OPEN TERMINAL" displays the modal within 500ms.
- **Criteria 2**: Sending `/status` from the dashboard terminal receives a valid response from the bot.
- **Criteria 3**: Trade approval messages appear with a clickable button that successfully triggers the `/approve` logic.
- **Criteria 4**: All messages sent/received match the Telegram bot conversation.
