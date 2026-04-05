# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

The "Elite Micro-Investor Bot" transforms the existing arbitrage-heavy system into a high-performance personal investor agent optimized for low-budget ($10-$500) capital efficiency. This implementation introduces a WebSocket event-driven architecture with Redis-backed order book shadowing for zero-latency execution, an automated "Idle-Cash Sweep" service (SGOV/MMF), and a "Federated Swarm Intelligence" layer for global strategy optimization. Key retail-centric features include fractional share execution via Trading 212, a 2% friction-cost guardrail, and interactive "What-If" visualizations with Telegram voice synthesis for enhanced user retention.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: `FastMCP`, `pandas`, `statsmodels`, `python-telegram-bot`, `yfinance`, `redis`, `websockets`, `openai` (TTS), `scipy` (Monte Carlo), `pydantic`  
**Storage**: SQLite (Primary), Redis (Shadow Order Book/Cache)  
**Testing**: `pytest`  
**Target Platform**: Linux (Ubuntu/Debian)  
**Project Type**: Multi-Agent Financial Trading System / Personal Assistant  
**Performance Goals**: <50ms latency for trade evaluation against local shadow book; 100% capital efficiency via daily sweeps.  
**Constraints**: <2% friction per trade; NYSE/NASDAQ hours (14:30-21:00 WET); Max 0.25x Kelly Criterion.  
**Scale/Scope**: Support for 100+ concurrent fractional positions across uncorrelated assets.


## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Implementation Strategy |
|-----------|--------|--------------------------|
| **I. Capital Preservation** | ✅ PASS | Fractional positions sized by Kelly Criterion (max 0.25x); 2% fee-veto via `FeeAnalyzer`. |
| **II. Mechanical Rationality** | ✅ PASS | Data-driven trade thesis from aggregated analyst signals (Bull, Bear, Fundamental). |
| **III. Total Auditability** | ✅ PASS | Every trade/veto recorded in a `TradeThesis` and "Thought Journal" (SQLite). |
| **IV. Strict Operation** | ✅ PASS | Mandatory enforcement of NYSE/NASDAQ hours in `monitor.py` (checked by `monitor_service`). |
| **V. Virtual-Pie First** | ✅ PASS | Portfolio managed as independent programatic structures, reconciled against T212 API state. |

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
