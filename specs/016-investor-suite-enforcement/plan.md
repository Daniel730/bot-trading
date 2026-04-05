# Implementation Plan: Investor Suite Architectural Enforcement

**Branch**: `016-investor-suite-enforcement` | **Date**: 2026-04-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/016-investor-suite-enforcement/spec.md`

## Summary

This feature enforces critical architectural rules and fixes identified in the production QA process for the low-budget investor suite. Key areas include Statistical Arbitrage math (OLS intercept), brokerage safety fallbacks for $0.00 commitments, friction math normalization, execution limit validation (T212), regional compliance fallbacks for hedging (EU UCITS), and system stability through robust multi-agent orchestration.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: `statsmodels`, `pandas`, `asyncio`, `yfinance`, `requests`  
**Storage**: SQLite (existing)  
**Testing**: `pytest`  
**Target Platform**: Linux / Docker  
**Project Type**: Trading Bot / Multi-agent system  
**Performance Goals**: N/A (Consistency and Reliability focused)  
**Constraints**: Zero-tolerance for $0.00 commitment orders; < 1.5% friction validation.  
**Scale/Scope**: Core service updates across 4 primary modules.

## Project Structure

### Documentation (this feature)

```text
specs/016-investor-suite-enforcement/
├── plan.md              # This file
├── spec.md               # Feature specification
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # To be generated
```

### Source Code (repository root)

```text
src/
├── agents/
│   └── orchestrator.py      # Stability fix (asyncio.gather)
├── services/
│   ├── arbitrage_service.py # Math fix (OLS intercept)
│   ├── brokerage_service.py # Safety (fallback price) & Limits (increments)
│   └── risk_service.py      # Friction (flat spread conversion) & Compliance (UCITS)
tests/
├── integration/
└── unit/
```

**Structure Decision**: Standard single project structure using established `src/services` and `src/agents` layout.
