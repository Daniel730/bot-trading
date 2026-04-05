# Implementation Plan: Resolve Production Rigor Gaps

**Branch**: `017-resolve-production-gaps` | **Date**: 2026-04-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/017-resolve-production-gaps/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

This feature resolves critical gaps identified in the production rigor checklist by implementing industrial-grade safety mechanisms: a retry policy with exponential backoff for price data, a system-wide circuit breaker for API stability, hardcoded EU UCITS compliance mappings for hedging, and strict friction-based rejection rules for micro-budgets.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: `statsmodels`, `pandas`, `asyncio`, `tenacity` (for retries), `requests`  
**Storage**: SQLite (for system status and failure tracking)  
**Testing**: `pytest`, `pytest-asyncio`  
**Target Platform**: Linux server / Docker  
**Project Type**: Trading Bot / Quantitative Arbitrage  
**Performance Goals**: < 1s latency for circuit breaker evaluation; 100% adherence to backoff schedule.  
**Constraints**: Zero execution of trades under $5.00 with >1.5% friction; strict intercept requirement for OLS.  
**Scale/Scope**: Core service updates affecting 4 modules: `brokerage_service.py`, `risk_service.py`, `arbitrage_service.py`, and `orchestrator.py`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Capital Preservation | ✅ PASS | Directly reinforced by FR-007 (Friction Reject) and FR-004 (Degraded Mode). |
| II. Mechanical Rationality | ✅ PASS | FR-008 ensures statistical models use an intercept for structural correctness. |
| III. Total Auditability | ✅ PASS | FR-006 mandates logging critical alerts for hedge bypasses. |
| IV. Strict Operation | ✅ PASS | No violations; safety measures enhance reliability during NYSE hours. |
| V. Virtual-Pie First | ✅ PASS | No impact on Pie management; operates at the execution safety layer. |

## Project Structure

### Documentation (this feature)

```text
specs/017-resolve-production-gaps/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/
├── agents/
│   └── orchestrator.py      # Circuit Breaker & Degraded Mode
├── services/
│   ├── arbitrage_service.py # OLS add_constant fix
│   ├── brokerage_service.py # Price rejection logic
│   ├── data_service.py      # Exponential backoff (tenacity)
│   └── risk_service.py      # EU UCITS Mapping & Friction Reject
├── models/
│   └── persistence.py       # Persistence for failure counts & status
```

**Structure Decision**: Standard single project structure. We will enhance existing services and add a persistent state for the circuit breaker in the database.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(No violations detected)
