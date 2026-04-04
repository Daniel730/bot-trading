# Implementation Plan: Embedded Telegram Terminal in Dashboard

**Branch**: `012-embedded-telegram-terminal` | **Date**: 2026-04-04 | **Spec**: `/specs/012-embedded-telegram-terminal/spec.md`
**Input**: Feature specification from `/specs/012-embedded-telegram-terminal/spec.md`

## Summary
Implement a responsive modal or card in the dashboard that embeds a direct Telegram chat interface. This allows investors to monitor and approve trade signals (HITL) without leaving the command station, improving operational efficiency while maintaining the bot's core risk management workflow.

## Technical Context

**Language/Version**: Python 3.11 (Backend), Vanilla JavaScript/HTML/CSS (Dashboard)
**Primary Dependencies**: `FastMCP`, `python-telegram-bot` (Backend), `tg://` protocol or Telegram Web Widget (Frontend)
**Storage**: SQLite (Existing persistence for signals/logs)
**Testing**: `pytest` (Integration tests for bot communication)
**Target Platform**: Linux (Server), Web Browser (Dashboard)
**Project Type**: Web Application + Bot Interface
**Performance Goals**: Modal open time < 500ms, Bot response latency < 1s
**Constraints**: Telegram security policies (X-Frame-Options), Cross-origin restrictions
**Scale/Scope**: 1 Dashboard interface, 1 Telegram bot interaction point

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|-----------|-------|--------|
| I. Capital Preservation | Does this bypass risk veto? No, it facilitates the human-in-the-loop approval process. | ✅ PASS |
| II. Mechanical Rationality | Is communication structured? Yes, uses standard Telegram bot commands. | ✅ PASS |
| III. Auditability Total | Are interactions logged? Yes, all commands sent via the terminal MUST be logged in the Thought Journal. | ✅ PASS |
| IV. Operação Estrita | Does it respect market hours? Yes, the underlying bot only operates during NYSE/NASDAQ hours. | ✅ PASS |
| V. Virtual-Pie First | Does it impact asset management? No, it's a UI enhancement for the orchestrator. | ✅ PASS |

## Project Structure

### Documentation (this feature)

```text
specs/012-embedded-telegram-terminal/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (generated later)
```

### Source Code

```text
dashboard/
├── index.html           # Add modal/terminal structure
├── style.css            # Add terminal styling
└── app.js               # Logic for opening terminal and handling states

src/
├── services/
│   ├── notification_service.py # Ensure bot links are provided to dashboard
│   └── dashboard_service.py    # API to fetch active bot session/link
```

**Structure Decision**: Integrated into existing `dashboard/` (frontend) and `src/` (backend services).

## Complexity Tracking

*No violations detected.*
