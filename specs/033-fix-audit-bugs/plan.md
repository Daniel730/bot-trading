# Implementation Plan: Audit Bug Fixes & System Hardening

**Branch**: `033-fix-audit-bugs` | **Date**: 2026-04-12 | **Spec**: [/specs/033-fix-audit-bugs/spec.md](/specs/033-fix-audit-bugs/spec.md)
**Input**: Feature specification from `/specs/033-fix-audit-bugs/spec.md`

## Summary

This feature addresses 17 identified audit bugs ranging from critical financial risk (missing awaits in risk/cash services) to security regressions (hardcoded credentials) and concurrency issues (list corruption, thread exhaustion). The technical approach involves strict asynchronous consistency, removal of static secrets in favor of environment-driven configuration, and hardening of the Java execution engine with non-blocking patterns and null safety.

## Technical Context

**Language/Version**: Python 3.11, Java 17+ (Execution Engine)  
**Primary Dependencies**: FastMCP, gRPC, Project Reactor (Java), asyncio (Python), pydantic  
**Storage**: SQLite (Portfolio/Signals), PostgreSQL (Audit/Ledger), Redis (Idempotency/Telemetry)  
**Testing**: pytest (Python), JUnit (Java)  
**Target Platform**: Linux (Docker)
**Project Type**: Distributed Trading System (Agents + Execution Engine)  
**Performance Goals**: <1ms gRPC RTT, 1000 req/s on Java engine, 100μs clock sync  
**Constraints**: 6 decimal places for fractional shares, NYSE/NASDAQ hours enforcement, <1.5% friction for micro-investments  
**Scale/Scope**: System-wide hardening across 17 distinct identified points in Python and Java services.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|-----------|-------|--------|
| I. Preservação de Capital | Ensuring auto-hedging and liquidation protocols actually run (fixing awaits). | ✅ PASS |
| II. Racionalidade Mecânica | Removing hardcoded secrets; using environment-driven data. | ✅ PASS |
| III. Auditabilidade Total | Fixing signal mutation to ensure logs and state are consistent. | ✅ PASS |
| IV. Operação Estrita | Defining REGION and fixing EU hedge reachability. | ✅ PASS |
| V. Virtual-Pie First | Hardening portfolio retrieval for accurate reconciliation. | ✅ PASS |

## Project Structure

### Documentation (this feature)

```text
specs/033-fix-audit-bugs/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (generated separately)
```

### Source Code (repository root)

```text
src/
├── services/
│   ├── risk_service.py              # Fix T-01
│   ├── cash_management_service.py   # Fix A-01
│   └── dashboard_service.py         # Fix S-02, S-03
├── monitor.py                       # Fix A-03, S-07
├── orchestrator.py                  # Fix S-07
├── config.py                        # Fix S-01
└── utils.py                         # Fix deprecations (loop access)

execution-engine/src/main/java/.../
└── ExecutionServiceImpl.java        # Fix J-01, J-02, J-03

tests/
├── unit/
│   ├── test_risk_service.py         # Regression for T-01
│   ├── test_cash_service.py         # Regression for A-01
│   └── test_brokerage.py            # Fix S-08
└── integration/
    └── test_execution_engine.py      # Regression for J-*
```

**Structure Decision**: Single repository with Python source in `src/` and Java execution engine in `execution-engine/`. Edits will target existing services and models to resolve identified bugs.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
