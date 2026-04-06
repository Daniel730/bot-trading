# Implementation Plan: Atomic Multi-Leg Execution

**Branch**: `025-atomic-multi-leg-execution` | **Date**: 2026-04-06 | **Spec**: [/specs/025-atomic-multi-leg-execution/spec.md]
**Input**: Feature specification from `/specs/025-atomic-multi-leg-execution/spec.md`

## Summary

This feature addresses "Critical Vulnerability #5: Naked Directional Exposure" in the Java Execution Engine. The existing logic only processed the first leg of a trade request, discarding others and creating unhedged positions. The new approach implements strict all-or-nothing validation across all legs before any order is sent to the broker. Audit logging is also enhanced to persist individual leg states with a unified correlation ID.

## Technical Context

**Language/Version**: Java 21  
**Primary Dependencies**: gRPC, R2DBC, Reactor (Project Reactor), Micrometer, Slf4j  
**Storage**: PostgreSQL (Trade Ledger), Redis (Idempotency)  
**Testing**: JUnit 5, Testcontainers (PostgreSQL), Mockito  
**Target Platform**: Linux (Docker)
**Project Type**: gRPC Web Service  
**Performance Goals**: Validation latency < 5ms for 2-leg trades  
**Constraints**: < 50ms total internal processing time (Latency Guard)  
**Scale/Scope**: Institutional-grade high-frequency arbitrage execution  

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I: Prioridade à Preservação de Capital**: PASS. This feature explicitly prevents naked directional exposure, the biggest risk to capital in arbitrage.
- **Principle III: Auditabilidade Total**: PASS. Multi-leg audit records ensure "White Box" transparency for every component of a trade.
- **Principle IV: Operação Estrita**: PASS. Latency checks ensure trades only occur within valid market conditions.

## Project Structure

### Documentation (this feature)

```text
specs/025-atomic-multi-leg-execution/
├── plan.md              # This file
├── research.md          # Multi-leg gRPC and R2DBC batching research
├── data-model.md        # trade_ledger schema and TradeAudit record
├── quickstart.md        # testing steps with grpcurl
├── contracts/           # execution.proto copy
└── tasks.md             # Implementation tasks
```

### Source Code (repository root)

```text
execution-engine/
├── src/main/java/com/arbitrage/engine/
│   ├── api/
│   │   └── ExecutionServiceImpl.java     # Refactored for atomic validation
│   ├── persistence/
│   │   └── TradeLedgerRepository.java   # Added saveAudits batching
│   └── core/models/
│       └── ExecutionLeg.java            # Standard leg model
└── src/test/java/com/arbitrage/engine/integration/
    └── ExecutionIntegrationTest.java    # Added multi-leg atomic failure test
```

**Structure Decision**: Standard Java project structure within the `execution-engine` directory.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| R2DBC Batching | Performance and atomicity of audits | Individual inserts would increase latency and risk orphaned records |
