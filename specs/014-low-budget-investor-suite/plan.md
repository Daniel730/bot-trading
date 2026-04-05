# Implementation Plan: Low-Budget Investor Suite & Portfolio Manager

**Branch**: `014-low-budget-investor-suite` | **Date**: 2026-04-05 | **Spec**: [specs/014-low-budget-investor-suite/spec.md]
**Input**: Feature specification from `/specs/014-low-budget-investor-suite/spec.md`

## Summary

Implement a retail-focused investment suite for micro-budgets ($10-$500). Key features include fractional share trading via Trading 212, a fee-aware risk interceptor, an automated Dollar-Cost Averaging (DCA) service, and a "Portfolio Manager" orchestrator agent. The technical approach involves updating existing trading models for value-based ordering and introducing new agents for macro context and "Explainable AI" investment justifications.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: `FastMCP`, `pandas`, `statsmodels`, `python-telegram-bot`, `requests`, `yfinance`, `tenacity`  
**Storage**: SQLite (Arbitrage pairs, Signal records, Virtual Pie state, Trade Ledger)  
**Testing**: `pytest`  
**Target Platform**: Linux (Docker-based deployment)
**Project Type**: Algorithmic Trading Bot with Telegram Terminal Interface  
**Performance Goals**: Fractional trade execution < 5s; DCA execution within 60m of schedule.  
**Constraints**: Friction costs (fees/spread) MUST be < 1.5% (default/configurable). Strict NYSE/NASDAQ hours.  
**Scale/Scope**: Supports micro-investments ($1+) across fractional-enabled stocks and ETFs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Prioridade à Preservação de Capital**: The "Fee Analyzer" directly implements the capital preservation mandate by auto-rejecting high-friction trades.
- [x] **Racionalidade Mecânica**: Use of `FastMCP` for data/execution. Portfolio Manager uses semantic validation to filter analyst noise.
- [x] **Auditabilidade Total**: "Investment Thesis" generation fulfills the "Thought Journal" requirement, providing natural language justifications for all trades.
- [x] **Operação Estrita**: DCA and Manager services will be bound by NYSE/NASDAQ regular hours (unless in DEV_MODE).
- [x] **Virtual-Pie First**: Portfolio Strategies are treated as programmatic structures independent of brokerage-side pie implementations.

## Project Structure

### Documentation (this feature)

```text
specs/014-low-budget-investor-suite/
├── spec.md              # Original feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── checklists/          # Requirement validation
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── agents/
│   ├── portfolio_manager_agent.py    # NEW: Orchestrator
│   └── macro_economic_agent.py       # NEW: Macro context
├── models/
│   └── trading_models.py             # UPDATE: Value-based orders
├── services/
│   ├── dca_service.py                # NEW: Recurring investments
│   ├── brokerage_service.py          # UPDATE: Fractional execution
│   ├── risk_service.py               # UPDATE: Fee Analyzer logic
│   └── agent_log_service.py          # UPDATE: Thesis generation
└── prompts.py                         # UPDATE: New agent personas

tests/
├── unit/
│   ├── test_fee_analyzer.py
│   ├── test_dca_scheduler.py
│   └── test_fractional_math.py
└── integration/
    └── test_portfolio_orchestration.py
```

**Structure Decision**: Option 1 (Single project) as the current codebase is a unified Python/FastMCP application.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
