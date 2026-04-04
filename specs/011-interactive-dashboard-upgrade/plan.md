# Implementation Plan: Interactive Dashboard Upgrade

**Branch**: `011-interactive-dashboard-upgrade` | **Date**: 2026-04-04 | **Spec**: `/specs/011-interactive-dashboard-upgrade/spec.md`

## Summary
Transform the existing static-ish dashboard into a high-fidelity, interactive "Quantitative Command Center" that displays real-time portfolio metrics (Revenue, Investments, Profit Production) and live trading signals (Possible Buy/Sell) using SSE.

## Technical Context
- **Backend**: FastAPI (existing in `src/services/dashboard_service.py`).
- **Data Source**: SQLite (queries for financial metrics) + `DashboardState` (live signal events from `Monitor`).
- **Frontend**: Vanilla JS (modernized) with Lucide Icons and CSS Grid/Flexbox for a responsive "HUD" layout.
- **Communication**: SSE (Server-Sent Events) for low-latency state updates.

## Constitution Check
- **I. Preservation of Capital**: ✅ Visual monitoring of real-time PnL and sector exposure reduces the risk of undetected "fat finger" or logic errors.
- **II. Mechanical Rationality**: ✅ The dashboard visually maps the bot's deterministic reasoning (Z-scores, integrity scores) to the UI.
- **III. Total Auditability**: ✅ The Thought Journal is integrated into the HUD, providing a continuous record of bot decisions.

## Project Structure

### Documentation
```text
specs/011-interactive-dashboard-upgrade/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Data source and UI decisions
├── data-model.md        # Dashboard state and metric queries
└── tasks.md             # Actionable tasks
```

### Source Code
```text
src/
└── services/
    └── dashboard_service.py # UPDATED: Expanded metrics and background updates
dashboard/
└── index.html              # UPDATED: Interactive HUD with new components
```

## Phase 0: Research (Completed)
- **Decision**: Polling frequency for DB metrics set to 10s. SSE frequency for live events remains real-time.
- **Decision**: Keep Vanilla JS for zero build-step overhead while making it modular.

## Phase 1: Design & Contracts
- **Data Model**: Metrics for Revenue, Investments, and Profit Production defined.
- **Contracts**: SSE payload expanded to include `{revenue, investments, daily_profit, signals_list}`.

## Phase 2: Implementation
- **Step 1**: Update `DashboardService` with metric-gathering logic.
- **Step 2**: Modernize `dashboard/index.html` with the new HUD layout.
- **Step 3**: Connect the monitor's signal pipeline to the dashboard.
- **Step 4**: Add "Possible Buy/Sell" visual alerts.

## Phase 3: Validation
- **Method**: Manual inspection during a simulated trading session (Shadow Mode).
- **Tools**: `scripts/test_dashboard_data.py` for mocking high-load signal scenarios.
