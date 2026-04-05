# Implementation Plan: 24/7 Crypto Development Mode

**Branch**: `006-crypto-dev-testing` | **Date**: 2026-03-31 | **Spec**: `/specs/006-crypto-dev-testing/spec.md`
**Input**: Feature specification for development purposes, focusing on a 24/7 market (Crypto) to validate connectivity and logic.

## Summary

Implement a `DEV_MODE` that bypasses NYSE/NASDAQ hour restrictions by switching to Crypto pairs (BTC-USD, ETH-USD) via `yfinance`. This allows for end-to-end testing of the `DataService`, `ArbitrageMonitor`, and Agent Orchestration during weekends or off-hours.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: `FastMCP`, `yfinance`, `pandas`, `statsmodels`, `tenacity`  
**Storage**: SQLite  
**Testing**: `pytest`  
**Target Platform**: Linux  
**Project Type**: CLI / Trading Bot  
**Performance Goals**: Orchestrator response < 10s; 100% connectivity success in DEV_MODE.  
**Constraints**: Must not interfere with production operation; must explicitly warn when active.  
**Scale/Scope**: Instrumented testing mode for real-time data flow validation.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Justification / Action |
|-----------|--------|------------------------|
| I. Preservação de Capital | ✅ PASS | DEV_MODE will use crypto for data but simulate execution or use low-risk tickers. Risk layers remain active. |
| II. Racionalidade Mecânica | ✅ PASS | Data flow remains structured; only the source/market hours are modified. |
| III. Auditabilidade Total | ✅ PASS | All DEV_MODE cycles will be logged, including the explicit 5-minute warning. |
| IV. Operação Estrita | ⚠️ VIOLATION | **Justified**: Necessary for weekend development/testing. Mitigation: Prominent "DEV_MODE ACTIVE" warnings. |
| V. Virtual-Pie First | ✅ PASS | State management and reconciliation will be tested via this mode. |

## Project Structure

### Documentation (this feature)

```text
specs/006-crypto-dev-testing/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (N/A for this internal feature)
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
src/
├── config.py            # DEV_MODE flag and Crypto ticker config
├── monitor.py           # Hour bypass logic and warning logs
├── services/
│   ├── data_service.py  # Crypto data fetching (yfinance)
│   └── audit_service.py # Connectivity tracking instrumentation
```

**Structure Decision**: Standard single project structure. Modifications primarily in `src/config.py`, `src/monitor.py`, and `src/services/`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| IV. Operação Estrita | To enable development during weekends and off-hours. | Hardcoding hours would require manual revert and risks accidental production bypass. `DEV_MODE` flag is safer and auditable. |
