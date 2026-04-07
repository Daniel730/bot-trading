# Feature Specification: Decoupled Fundamental RAG (Asynchronous SEC Analysis)

**Feature Branch**: `024-decoupled-fundamental-rag`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "feature="Decoupled Fundamental RAG (Asynchronous SEC Analysis)" context="src/agents/orchestrator.py,src/agents/fundamental_analyst.py,src/services/redis_service.py" requirements="1. Remove all synchronous/blocking fundamental_analyst network calls from the Orchestrator's critical path. 2. Architect a background worker (or cron loop) that periodically computes and caches fundamental scores in Redis. 3. Refactor Orchestrator to pull structural integrity scores via sub-millisecond Redis cache reads, defaulting to a neutral score (50) if the cache is empty.""

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Real-time Signal Debate with Cached Fundamentals (Priority: P1)

As a trading bot orchestrator, I want to perform signal evaluation without waiting for external SEC RAG calls, so that the total decision latency stays under 100ms and doesn't trigger slippage rejections in the execution engine.

**Why this priority**: Latency-critical. Synchronous I/O in the execution path is currently causing a 100% trade rejection rate.

**Independent Test**: Mock a 10-second delay in the Fundamental Analyst's RAG process. The Orchestrator should still produce a decision within 100ms by reading from the Redis cache.

**Acceptance Scenarios**:

1. **Given** a cached structural integrity score of 85 for "AAPL" in Redis, **When** a signal for "AAPL" is evaluated, **Then** the decision path uses 85 and completes in under 50ms.
2. **Given** no cached score for "TSLA" in Redis, **When** a signal for "TSLA" is evaluated, **Then** the orchestrator uses a neutral default score of 50 and completes in under 50ms.

---

### User Story 2 - Asynchronous Fundamental Score Updates (Priority: P2)

As a system administrator, I want the fundamental analysis to run in the background on a schedule, so that my cached data reflects the most recent SEC filings without impacting trade execution speed.

**Why this priority**: Ensures the "Materialized View" in Redis stays relevant for decision-making.

**Independent Test**: Manually trigger the background worker. Verify that the score for a specific ticker is updated in Redis within the expected processing time for that worker.

**Acceptance Scenarios**:

1. **Given** the background worker is active, **When** a new SEC filing for "MSFT" is detected, **Then** the worker eventually updates `sec:integrity:MSFT` in Redis with the new calculated score.
2. **Given** the background worker encounters a network error, **Then** the existing Redis cache entry remains untouched (preventing data corruption/emptying).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Orchestrator MUST NOT call any synchronous network functions (e.g., `fundamental_analyst.analyze_ticker`) during the `evaluate_signal` lifecycle.
- **FR-002**: System MUST provide a background execution context (Worker or Cron) to periodically execute the Fundamental Analyst logic for relevant tickers.
- **FR-003**: Background worker MUST cache the calculated structural integrity scores in Redis using the key pattern `sec:integrity:{ticker}`.
- **FR-004**: The Orchestrator MUST retrieve the fundamental score from Redis using an $O(1)$ read operation.
- **FR-005**: The Orchestrator MUST default to a score of 50 if the Redis cache for a ticker is empty or unreachable.

### Key Entities

- **Structural Integrity Score**: A value from 0-100 representing the fundamental health of a ticker based on SEC filings.
- **Ticker Cache**: A Redis-based key-value store mapping tickers to their latest integrity scores.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Orchestrator decision latency (from signal received to gRPC request sent) MUST be consistently under 100ms.
- **SC-002**: 0% trade rejections in the Java Execution Engine caused by "Stale Alpha" or "Latency Timeout" when fundamental analysis is active.
- **SC-003**: Background worker successfully refreshes 100% of tracked ticker scores at least once per 24 hours (or per SEC filing release).
- **SC-004**: Redis read latency for fundamental scores MUST be under 5ms (P99).

## Assumptions

- [Assumption about scope]: Fundamental data is relatively static (quarterly/daily) compared to L2 order book movements.
- [Assumption about environment]: Redis is available and configured for high availability.
- [Assumption about defaults]: A neutral score of 50 is acceptable for new tickers until the first background analysis completes.
