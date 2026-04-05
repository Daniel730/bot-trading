# Tasks: Interactive Dashboard Upgrade

## 1. Summary
This document outlines the actionable tasks for the Interactive Dashboard Upgrade, organized by user story to ensure incremental delivery and independent testing.

## 2. Implementation Strategy
- **MVP First**: Focus on real-time portfolio metrics (Revenue, Investments) in User Story 1.
- **Incremental Delivery**: Deliver the foundational backend updates (Phase 2) before the interactive frontend (Phase 3 & 4).
- **Parallelism**: Frontend UI components (T006-T008) can be developed in parallel with backend metric polling (T003-T004).

## 3. Dependency Graph
```text
Phase 1 (Setup)
  └── Phase 2 (Foundational)
        ├── Phase 3 (US1: Real-Time Dashboard)
        │     └── Phase 4 (US2: Visual Trading Signals)
        └── Phase 5 (Polish)
```

## 4. Parallel Execution Examples
- **US1**: `T006` (Metric Cards) and `T007` (Thought Journal Integration) can be implemented simultaneously.
- **US2**: `T009` (Possible Buy/Sell Alerts) and `T010` (Z-score Feed) are independent UI tasks.

## 5. Phases

### Phase 1: Setup
- [X] T001 Create `scripts/test_dashboard_data.py` to mock bot signals and verify UI rendering.
- [X] T002 Ensure `dashboard/` directory is prepared for modular JS/CSS separation.

### Phase 2: Foundational
- [X] T003 Implement SQL queries/methods in `src/models/persistence.py` and `DashboardService` for Revenue, Investment, Daily Profit, and Available Cash.
- [X] T004 Expand `DashboardState` in `src/services/dashboard_service.py` to include `portfolio_metrics` and `active_signals`.
- [X] T005 Implement a background task in `src/services/dashboard_service.py` to poll metrics from `PersistenceManager` every 10 seconds.

### Phase 3: User Story 1 - Real-Time Dashboard
**Story Goal**: Implement real-time portfolio performance tracking.
**Independent Test**: Access the dashboard and verify that "Total Invested" and "Revenue" match the mock data from `scripts/test_dashboard_data.py`.

- [X] T006 [P] [US1] Create "Metric Cards" component in `dashboard/index.html` for Revenue, Investments, Daily Profit, and Available Cash.
- [X] T007 [P] [US1] Integrate the `Thought Journal` log directly into the UI in `dashboard/index.html`.
- [X] T008 [US1] Update the SSE `/stream` endpoint in `src/services/dashboard_service.py` to broadcast the new portfolio metrics.

### Phase 4: User Story 2 - Visual Trading Signals
**Story Goal**: Visualizing trading opportunities and bot actions.
**Independent Test**: Mock a Z-score > 2.0 and verify that the pair appears as "Possible Buy/Sell" in the UI.

- [X] T009 [P] [US2] Implement "Possible Buy/Sell" visual alerts in `dashboard/index.html` based on Z-score thresholds.
- [X] T010 [P] [US2] Create a live "Signals Feed" in `dashboard/index.html` showing active pairs and their Z-scores.
- [X] T011 [US2] Update `src/monitor.py` to push granular signal updates (Z-scores) to the `DashboardService`.

### Phase 5: Polish & Cross-Cutting Concerns
- [X] T012 Add "Revenue Growth" sparkline and "Sector Distribution" pie chart using Chart.js in `dashboard/index.html` (FR-005).
- [X] T013 Refactor `dashboard/index.html` CSS for better responsiveness on mobile devices.
- [X] T014 Conduct a final audit for performance (latencies < 2s) as per NFR-001.
- [X] T015 [P] Implement simple authentication (e.g., token-based header or environment IP gate) in `src/services/dashboard_service.py` as per NFR-002.
