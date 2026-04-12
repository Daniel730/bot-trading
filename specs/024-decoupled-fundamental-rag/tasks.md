# Tasks: Decoupled Fundamental RAG (024-decoupled-fundamental-rag)

**Input**: Design documents from `/specs/024-decoupled-fundamental-rag/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)

## Phase 1: Setup & Foundational

**Purpose**: Infrastructure for background processing and Redis caching

- [X] T001 Create `src/daemons/` directory and `src/daemons/__init__.py`
- [X] T002 Implement `get_fundamental_score` and `set_fundamental_score` in `src/services/redis_service.py` with 24h TTL
- [X] T003 [P] Define `get_active_trading_universe` in `src/services/persistence_service.py` (query unique tickers from active pairs)

---

## Phase 2: User Story 2 - Asynchronous Fundamental Score Updates (Priority: P2)

**Goal**: Implement a process-isolated daemon to refresh SEC fundamental scores.

**Independent Test**: Run the daemon manually for a ticker and verify `redis-cli GET sec:integrity:{ticker}` returns the fresh score.

### Implementation for User Story 2

- [X] T004 [US2] Create standalone daemon skeleton in `src/daemons/sec_fundamental_worker.py`
- [X] T005 [US2] Integrate `FundamentalAnalyst` into the worker with a loop iterating through the trading universe
- [X] T006 [US2] Implement exponential backoff for SEC EDGAR (HTTP 429) using `tenacity` or custom logic in the worker
- [X] T007 [US2] Create `Dockerfile.daemon` to enable isolated process execution
- [X] T008 [US2] Update `docker-compose.backend.yml` to include the `sec-worker` service

**Checkpoint**: Background worker is operational and populating Redis independently.

---

## Phase 3: User Story 1 - Real-time Signal Debate with Cached Fundamentals (Priority: P1) 🎯 MVP

**Goal**: Refactor Orchestrator to use sub-millisecond cached reads.

**Independent Test**: Mock 10s delay in `FundamentalAnalyst` and verify Orchestrator `ainvoke` completes in < 100ms.

### Implementation for User Story 1

- [X] T009 [US1] Refactor `Orchestrator.ainvoke` in `src/agents/orchestrator.py` to remove direct calls to `fundamental_analyst.analyze_ticker`
- [X] T010 [US1] Implement parallel Redis reads for fundamental scores in `Orchestrator.ainvoke` using `asyncio.gather`
- [X] T011 [US1] Implement neutral default score (50) logic for cache misses/expiry
- [X] T012 [US1] Emit high-priority telemetry metrics on fundamental cache misses via `src/services/telemetry_service.py`

**Checkpoint**: Signal evaluation latency reduced by several orders of magnitude.

---

## Phase 4: Polish & Performance

**Purpose**: Validation and documentation

- [ ] T013 [P] Add unit tests for `RedisService` fundamental score methods in `tests/unit/test_redis_service.py`
- [X] T014 [P] Update `docs/agents.md` with the new Decoupled RAG architecture
- [ ] T015 Verify end-to-end flow: Daemon updates Redis -> Orchestrator picks up score without latency

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Must be completed first.
- **Worker (Phase 2)**: Can be implemented before or alongside Phase 3.
- **Orchestrator (Phase 3)**: High priority (P1) for solving the latency deadlock.

### Parallel Opportunities

- T002, T003 can be done in parallel.
- Phase 2 and Phase 3 can be developed in parallel once Phase 1 is done.

---

## Implementation Strategy

### MVP First (P1 Story)

1. Complete Phase 1.
2. Complete US1 (Phase 3) using manual Redis sets for testing. This immediately fixes the "Stale Alpha" rejections.
3. **VALIDATE**: Orchestrator latency < 100ms.

### Incremental Delivery

1. Complete US2 (Phase 2) to automate the refresh logic.
2. Finalize telemetry and documentation.
