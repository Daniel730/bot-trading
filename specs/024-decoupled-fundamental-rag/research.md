# Research: Decoupled Fundamental RAG (Asynchronous SEC Analysis)

## Decision: Process-Isolated Background Daemon
**Decision**: Implement a standalone Python process (`src/daemons/sec_fundamental_worker.py`) running in a dedicated Docker container.

**Rationale**:
- SEC RAG involves heavy text parsing and LLM I/O that would block the Python GIL if run inside the Orchestrator process.
- Isolation prevents millisecond-level stalls in the main trading loop.
- Dedicated containers allow for independent scaling and monitoring of the fundamental pipeline.

## Decision: Deterministic Trading Universe
**Decision**: The daemon will extract all unique tickers from the PostgreSQL `active_pairs` table to define its work scope.

**Rationale**:
- Avoids "guessing" or reactive caching; we analyze every ticker we are potentially trading.
- Ensures the cache is pre-populated before a signal ever fires.
- Automatically scales as new pairs are added to the system by the quant desk.

## Decision: Redis Materialized View with 24h TTL
**Decision**: Store fundamental scores in Redis using the key `sec:integrity:{ticker}` with a 24-hour Time-To-Live (TTL).

**Rationale**:
- 24 hours is a safe window for fundamental data.
- If the worker fails, the data expires, preventing the orchestrator from using dangerously stale information.
- A missing cache entry signals a need for a fallback and an alert.

## Decision: High-Priority Metrics for Cache Misses
**Decision**: Every time the Orchestrator defaults to a score of 50 due to a cache miss/expiry, emit a high-priority log and metric via `TelemetryService`.

**Rationale**:
- Ensures the trading desk is notified if the fundamental analysis pipeline is down.
- Provides visibility into how often the bot is "flying blind".

## Decision: Exponential Backoff & Circuit Breakers for SEC EDGAR
**Decision**: Use the `tenacity` library or a custom decorator for exponential backoff on HTTP 429 (Rate Limit) errors from the SEC EDGAR API.

**Rationale**:
- The SEC EDGAR API has strict rate limits.
- Robust error handling prevents the daemon from crashing during outages or rate limiting events.

## Alternatives Considered
- **Direct Database Storage**: Too slow for the orchestrator's $O(1)$ requirement. Redis is preferred.
- **On-demand Refresh**: Still introduces latency if the cache is empty. Background pre-fetching is necessary for known tickers.
