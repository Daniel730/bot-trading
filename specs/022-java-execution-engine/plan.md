# Implementation Plan: High-Performance Execution Engine (The Muscle)

**Branch**: `022-java-execution-engine` | **Date**: 2026-04-05 | **Spec**: [/specs/022-java-execution-engine/spec.md]
**Input**: Feature specification from `/specs/022-java-execution-engine/spec.md`

## Summary
The "Muscle" layer is a Java 21 microservice designed for low-latency execution of arbitrage signals. It acts as the final risk gate by performing a deterministic "Walk the Book" VWAP calculation against live Level 2 (L2) liquidity. It communicates with the Python "Brain" via gRPC and uses a Dual-DB architecture (PostgreSQL via R2DBC for persistent audits, Redis via Lettuce for transient state) to ensure atomicity, auditability, and crash recovery.

## Technical Context

**Language/Version**: Java 21 (Mandatory for Virtual Threads support)  
**Primary Dependencies**: gRPC (Netty-shaded), R2DBC (PostgreSQL), Lettuce (Redis), Micrometer (Metrics), Jackson (JSON), LMAX Disruptor (Optional for internal queuing).  
**Storage**: PostgreSQL (Persistent Trade Ledger & Audits), Redis (In-flight Order Sync & Rate Limiting).  
**Testing**: JUnit 5, Mockito, Testcontainers (PostgreSQL/Redis integration).  
**Target Platform**: Linux (Distroless Docker Container).  
**Project Type**: High-performance, low-latency microservice.  
**Performance Goals**: < 2ms internal processing latency (P99); 10,000+ state updates per second.  
**Constraints**: 10-decimal precision using `BigDecimal`; Non-blocking I/O only; < 50ms total Brain-to-Exchange latency.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

1.  **Principle I (Capital Preservation)**: **PASS**. The "Walk the Book" algorithm and slippage veto are direct implementations of capital preservation.
2.  **Principle II (Mechanical Rationality)**: **PASS**. Uses deterministic mathematical logic for VWAP and gRPC for structured data exchange.
3.  **Principle III (Total Auditability)**: **PASS**. All execution attempts and rejections are persisted to `TradeLedger` in PostgreSQL.
4.  **Principle IV (Strict Operation)**: **PASS**. The engine obeys TTL constraints (`timestamp_ns`) to ensure signals are not executed outside their validity window.
5.  **Principle V (Virtual-Pie First)**: **PASS**. Supports multi-leg execution required for complex programmatic allocations.

## Project Structure

### Documentation (this feature)

```text
specs/022-java-execution-engine/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── execution.proto  # gRPC Contract
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
execution-engine/
├── build.gradle.kts     # Gradle Kotlin DSL
├── src/
│   ├── main/
│   │   ├── proto/       # gRPC definitions
│   │   ├── java/
│   │   │   ├── com.arbitrage.engine/
│   │   │   │   ├── Application.java
│   │   │   │   ├── api/ (gRPC Services)
│   │   │   │   ├── core/ (VWAP Logic, Math)
│   │   │   │   ├── persistence/ (R2DBC, Redis)
│   │   │   │   └── risk/ (Slippage Guards)
│   │   └── resources/
│   └── test/
│       ├── java/        # Unit and Integration tests
│       └── resources/
├── Dockerfile           # Distroless build
└── README.md
```

**Structure Decision**: The Java service is placed in a top-level `execution-engine/` directory to maintain a clean polyglot monorepo structure, separate from the Python `src/` directory.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | | |
