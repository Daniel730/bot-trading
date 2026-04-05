# Implementation Plan: Decoupled Fundamental RAG

**Feature Branch**: `024-decoupled-fundamental-rag`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: [specs/024-decoupled-fundamental-rag/spec.md]

## Technical Context

- **Tech Stack**: Python 3.11, Redis, Gemini (SEC RAG), Telemetry (Metrics).
- **Concurrency**: `asyncio` for non-blocking I/O in the Orchestrator.
- **Background Context**: Celery, APScheduler, or a standalone `asyncio` worker for SEC refresh.

## Constitution Check

- **Principle I: Prioridade à Preservação de Capital**: Decoupling prevents latency-driven rejections (opportunity cost) and ensures a reliable (even if slightly stale) fundamental view.
- **Principle II: Racionalidade Mecânica**: Decisions are based on structured data retrieved via sub-millisecond Redis reads.
- **Principle III: Auditabilidade Total**: Cache misses are logged and monitored, providing visibility into the "Materialized View" health.

## Research Summary

- **Asynchronous Worker**: We will implement a process-isolated standalone daemon (`src/daemons/sec_fundamental_worker.py`) that runs in its own Docker container.
- **Trading Universe**: The worker will query the PostgreSQL `active_pairs` table on startup to determine the deterministic set of tickers requiring analysis.
- **TTL Enforcement**: 24-hour Redis TTL to prevent stale data usage.
- **Telemetry**: High-priority alert on cache miss (defaulting to 50) using `TelemetryService`.

## Implementation Strategy

### Phase 1: Setup & Foundational
- [ ] Create `src/daemons/` directory and `sec_fundamental_worker.py` entry point.
- [ ] Update `RedisService` with fundamental cache methods.
- [ ] Define PostgreSQL query logic to extract unique tickers from `active_pairs`.

### Phase 2: Background Daemon (Process Isolation)
- [ ] Implement the `SECFundamentalWorker` with exponential backoff for SEC API limits.
- [ ] Integrate `FundamentalAnalyst` into the standalone daemon context.
- [ ] Create a dedicated `Dockerfile.daemon` for process isolation.

### Phase 3: Orchestrator Refactor (Latency Optimization)
- [ ] Remove all synchronous SEC RAG calls from `Orchestrator.ainvoke`.
- [ ] Implement sub-millisecond parallel Redis reads for ticker pairs.
- [ ] Implement neutral default (50) and high-priority telemetry on cache misses.

### Phase 4: Verification & Polish
- [ ] Load test the Orchestrator to ensure P99 latency < 100ms.
- [ ] Verify daemon resilience against SEC EDGAR rate limits.
- [ ] Document the "Materialized View" architecture in `docs/agents.md`.

## Technical Unknowns

(None. Architectural boundaries are locked for process isolation and deterministic universe.)
