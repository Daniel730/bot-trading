# Implementation Plan: Production-Grade Polish & Reliability Enforcement

**Branch**: `018-production-polish-rules` | **Date**: 2026-04-05 | **Spec**: [specs/018-production-polish-rules/spec.md]
**Input**: Feature specification from `/specs/018-production-polish-rules/spec.md`

## Summary

This plan updates the bot's core services to enforce production-grade reliability and risk controls. It focuses on persistent mathematical state for Kalman Filters, API rate-limit protection via caching, flash-crash slippage guards, dividend reinvestment safety, and absolute timezone synchronization with the NYSE.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: `FastMCP`, `pandas`, `statsmodels`, `pytz`, `redis`, `requests`, `tenacity`  
**Storage**: SQLite (Primary), Redis (Secondary/Cache)  
**Testing**: `pytest`  
**Target Platform**: Linux (Docker)
**Project Type**: Trading Bot / Web Service  
**Performance Goals**: <100ms internal latency, 5s TTL API caching  
**Constraints**: 1% slippage guard, Strictly NYSE regular hours (9:30 AM - 4:00 PM ET)  
**Scale/Scope**: Core reliability enhancement for production deployment.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Justification |
|-----------|--------|---------------|
| I. Prioridade à Preservação de Capital | ✅ PASS | Slippage guards (1%) and DRIP safety (min value) protect capital. |
| II. Racionalidade Mecânica | ✅ PASS | Persistent Kalman state ensures consistent model application across restarts. |
| III. Auditabilidade Total | ✅ PASS | All cached responses and state updates are logged via existing audit service. |
| IV. Operação Estrita | ✅ PASS | Timezone sync ensures operation strictly during NYSE hours. |
| V. Virtual-Pie First | ✅ PASS | Kalman state persistence is a key requirement for programmatic asset management. |

## Project Structure

### Documentation (this feature)

```text
specs/018-production-polish-rules/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
src/
├── services/
│   ├── arbitrage_service.py # Move Kalman persistence here
│   ├── brokerage_service.py # Implement API caching, slippage guards, DRIP logic
│   └── kalman_service.py    # Provide state for persistence
├── config.py                # Update NYSE hours
└── monitor.py               # Update timezone sync (pytz)

tests/
├── integration/
│   ├── test_kalman_persistence.py
│   └── test_brokerage_cache.py
└── unit/
    ├── test_slippage_guard.py
    └── test_drip_safety.py
```

**Structure Decision**: Standard single-project structure. Logic is encapsulated in existing service singletons.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
