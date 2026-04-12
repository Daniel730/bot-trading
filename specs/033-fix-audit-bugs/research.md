# Research: Audit Bug Fixes & System Hardening

This research phase addresses technical unknowns for the 17 identified audit bugs.

## 1. Asynchronous Consistency (Python)

### Decision: asyncio.get_running_loop() and Explicit Awaits
- **Rationale**: `asyncio.get_event_loop()` is deprecated in Python 3.10+ and fails in 3.12+ if no loop is already running. `asyncio.get_running_loop()` should be used within coroutines. All calls to `get_portfolio()` and cash management operations must be explicitly awaited.
- **Alternatives considered**: `asyncio.get_event_loop_policy()`. Rejected as it is lower-level and more complex than needed for standard service logic.

## 2. Concurrency Protection (Python)

### Decision: asyncio.Lock for self.active_signals
- **Rationale**: `monitor.py` mutates `self.active_signals` within `asyncio.gather`. Using an `asyncio.Lock` ensures atomic updates to the shared list, preventing corruption or inconsistent states.
- **Alternatives considered**: `ContextVar`. Rejected because `active_signals` is shared state across different scan tasks, not per-task local state.

## 3. Java gRPC Non-blocking Patterns

### Decision: Project Reactor with Dedicated Schedulers
- **Rationale**: The current `.block()` calls on gRPC handler threads exhaust the thread pool. Since the gRPC implementation is blocking-style (`StreamObserver`), we should wrap blocking DB/Redis calls in `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` or use a dedicated executor to offload the blocking work from the gRPC threads.
- **Alternatives considered**: Virtual Threads (Java 21). Rejected to maintain compatibility with Java 17 (if that's the current constraint) and to minimize migration risk.

## 4. Security Hardening

### Decision: Environment-only Secrets
- **Rationale**: Remove all default values for `POSTGRES_PASSWORD` and `DASHBOARD_TOKEN` in `config.py` and `dashboard_service.py`. Enforce authentication even in `DEV_MODE=True` for the dashboard.
- **Implementation**: Use `Field(..., validation_alias=...)` without a default value to force environment variable configuration in production, or raise a warning/error at startup if missing.

## 5. System Robustness

### Decision: Rounding Trap and Bounded Lists
- **Rationale**: 
    - **Rounding Trap**: Implement a check in `brokerage_service.py` before order submission. If `quantity < 0.000001` (or relevant precision), raise a `ValidationError`.
    - **WebSocket Bounding**: Limit `self.active_connections` in `dashboard_service.py` to `MAX_CONNECTIONS=50`. Drop oldest connections or reject new ones if the limit is exceeded.
    - **Docker Healthcheck**: Verify the healthcheck URL in `docker-compose.yml` or `Dockerfile` and ensure it points to `/health` or a valid endpoint.
