# Historical Audit Note

This register captures an older multi-environment audit and is preserved for traceability. Several findings have since been fixed or changed. Use `docs/tofix.md` plus current source/tests as the active backlog.

# Bug & Error Register — Full Multi-Environment Audit
**Last updated**: 2026-04-12 | Audited: Python async, Java engine, trading logic, security/infra

Severity: **Critical** → **High** → **Medium** → **Low**

---

## Critical — System-Breaking

### C-02 · `_recover_timeout_order()` Is `async def` Called Without `await` in Sync Function
**File**: `src/services/brokerage_service.py:151`  
**Status**: Persists  
**Problem**: `place_market_order()` is plain `def`. On `requests.Timeout` it returns `self._recover_timeout_order(...)` which is `async def` — returns a bare coroutine. Caller then does `result.get("status")` → `AttributeError`. Every network timeout crashes silently.  
**Fix**: Make `place_market_order` async and await the call, or run recovery via `asyncio.get_running_loop().run_until_complete(...)`.

---

### T-01 · Missing `await` on `get_portfolio()` in `check_hedging()` — DEFCON-1 Never Executes
**File**: `src/services/risk_service.py:146`  
**Status**: New  
**Problem**: `check_hedging()` is `async def` but calls `portfolio = brokerage_service.get_portfolio()` without `await`. `get_portfolio()` is `async def`, so this assigns a bare coroutine to `portfolio`. The subsequent loop over `portfolio` raises `TypeError: 'coroutine' object is not iterable`. The entire DEFCON-1 auto-hedging protocol — the last line of defence during a market crash — **never executes**.  
**Fix**: Change to `portfolio = await brokerage_service.get_portfolio()`.

---

### A-01 · `cash_management_service.py` — `get_account_cash()` and `get_latest_price()` Called Without `await`
**File**: `src/services/cash_management_service.py:20, 46`  
**Status**: New  
**Problem**: `sweep_idle_cash()` and `liquidate_for_trade()` are both `async def`. Line 20 calls `brokerage_service.get_account_cash()` and line 46 calls `data_service.get_latest_price([...])` — both `async def` — without `await`. Both return unawaited coroutines. Cash sweep and trade liquidation logic never runs.  
**Fix**: Add `await` to both calls; ensure `asyncio.to_thread` wraps `get_account_cash` as it is blocking.

---

### S-01 · Hardcoded Default PostgreSQL Password
**File**: `src/config.py:37`  
**Status**: New  
**Problem**: `POSTGRES_PASSWORD: str = Field(default="bot_pass", ...)`. If the env var is unset the system boots with a known default password — silent security regression.  
**Fix**: Set `default=None` and add a `model_validator` that raises `ValueError` if password is falsy.

---

### S-02 · Hardcoded Default Dashboard Token
**File**: `src/services/dashboard_service.py:118`  
**Status**: New  
**Problem**: `raw_secret = os.getenv("DASHBOARD_TOKEN", "arbi-elite-2026")`. Any client knowing the published default can access the live dashboard with no other credential.  
**Fix**: Remove the default entirely; raise at startup if `DASHBOARD_TOKEN` is unset.

---

## High — Execution Correctness & Capital Safety

### H-01 · Idempotency Key Not Stable Across Retries
**File**: `src/services/brokerage_service.py:120`  
**Status**: Persists  
**Problem**: Fresh `uuid.uuid4()` per `place_market_order()` call. Broker sees each retry as a new order — duplicate fills.  
**Fix**: Derive `clientOrderId` as UUIDv5(`signal_id`) so retries produce the same key.

---

### H-03 · Blocking `requests` Calls Stall the Async Event Loop
**File**: `src/services/brokerage_service.py:141, 194, 262`  
**Status**: Persists  
**Problem**: Three sites make synchronous HTTP calls directly on the event loop:
- `place_market_order()` → `requests.post()` (up to 15 s)
- `check_dividends_and_reinvest()` → `self.get_account_cash()` directly (up to 30 s with retries)
- `place_value_order()` → `self.place_market_order()` without `asyncio.to_thread`  
**Fix**: Wrap all three with `await asyncio.to_thread(...)` or switch to `httpx.AsyncClient`.

---

### H-05 · All Pair Sectors Default to `Technology` — Wrong Beacon for Every Non-Tech Pair
**File**: `src/monitor.py:190-194`  
**Status**: Persists  
**Problem**: `signal_context` never includes `"sector"`. Orchestrator always defaults to `'Technology'` → checks NVDA for financial/energy/consumer pairs.  
**Fix**: Add `"sector": settings.PAIR_SECTORS.get(pair_id, "Technology")` to `signal_context`.

---

### A-03 · Race Condition on `self.active_signals` — List Corruption Under Load
**File**: `src/monitor.py:184-187, 213`  
**Status**: New  
**Problem**: `process_pair()` is called via `asyncio.gather()` for all pairs simultaneously. Inside each coroutine, `self.active_signals.append(...)` and `self.active_signals = [...]` mutate the shared list with no lock. Concurrent appends/reassignments can lose entries or corrupt the list state, causing signals to vanish from the dashboard or be double-counted.  
**Fix**: Protect mutations with an `asyncio.Lock()` held by `ArbitrageMonitor`, or replace with a `dict` keyed on `pair_id` for O(1) safe updates.

---

### S-03 · DEV_MODE Bypasses All Dashboard Authentication
**File**: `src/services/dashboard_service.py:114-116`  
**Status**: New  
**Problem**: `verify_token()` returns immediately if `settings.DEV_MODE is True` — no token required. If `DEV_MODE` is left `True` in a production deploy the dashboard is fully open.  
**Fix**: Remove the DEV_MODE shortcut from auth; use a separate dev-only token if needed.

---

### S-07 · Zero Test Coverage for Critical Execution Paths
**File**: `src/monitor.py:221, 481`; `src/agents/orchestrator.py:56, 72`  
**Status**: New  
**Problem**: `execute_trade()`, `_close_position()`, the DEGRADED_MODE veto (orchestrator line 56), and the macro regime veto (lines 72-76) have no unit or integration tests. The PnL calculation and order placement logic are entirely untested.  
**Fix**: Add async unit tests for each path using `IsolatedAsyncioTestCase` with `AsyncMock` broker.

---

### S-08 · `test_brokerage.py` — `get_portfolio()` Called Without `await` in Sync Test
**File**: `tests/integration/test_brokerage.py:50`  
**Status**: New  
**Problem**: `self.service.get_portfolio()` is `async def` but called without `await` in sync `unittest.TestCase`. Returns coroutine; `assertEqual(len(result), 1)` raises `TypeError`. Test always fails.  
**Fix**: Convert to `IsolatedAsyncioTestCase` and add `await`.

---

### J-01 · `L2OrderBook` Not Null-Checked Before `VwapCalculator`
**File**: `execution-engine/.../api/ExecutionServiceImpl.java:105-106`  
**Status**: New  
**Problem**: `l2FeedService.getLatestBook()` can return `null` (no null contract on the interface). Result is passed directly to `vwapCalculator.calculateVwap(book, ...)` without a null guard. Any empty or unwarmed book causes NPE inside `VwapCalculator` when accessing `book.asks()` / `book.bids()`.  
**Fix**: Add `if (book == null) { handleError(...); return; }` before the VWAP call.

---

### J-02 · `.block()` Called in gRPC Handler Thread (`getTradeStatus`)
**File**: `execution-engine/.../api/ExecutionServiceImpl.java:185, 196`  
**Status**: New  
**Problem**: `getTradeStatus()` runs on a gRPC handler thread and calls `.block()` twice (Redis + DB queries). A slow DB or Redis stalls the thread indefinitely, exhausting the handler thread pool and preventing all other gRPC calls from being processed.  
**Fix**: Convert `getTradeStatus` to subscribe reactively and call `responseObserver` from the callback, or use virtual-thread-friendly blocking only if the executor is configured to support it.

---

### J-03 · Double `responseObserver.onCompleted()` — gRPC Contract Violation
**File**: `execution-engine/.../api/ExecutionServiceImpl.java:160-176`  
**Status**: New  
**Problem**: The reactive chain has two terminal paths that both call `responseObserver.onNext()` + `onCompleted()`: the success flatMap and the `doOnError` → `handleError` path. If an error fires after the success response has already been sent, `handleError` calls `onCompleted()` a second time — violating the gRPC single-terminal-signal contract and potentially crashing the channel.  
**Fix**: Track a `AtomicBoolean responded` flag; only send the terminal signal once.

---

## Medium — Data Integrity & Reliability

### M-01 · `TradeLedgerRepository.getStatus()` Leaks Database Connections
**File**: `execution-engine/.../persistence/TradeLedgerRepository.java:72-79`  
**Status**: Persists  
**Fix**: Chain `.doFinally(signal -> connection.close())` or use `Flux.usingWhen()`.

---

### M-02 · `TradeLedgerRepository.saveAudits()` Leaks Connection on Error Rollback
**File**: `execution-engine/.../persistence/TradeLedgerRepository.java:66-68`  
**Status**: Persists  
**Fix**: Use `Mono.usingWhen(...)` with `Connection::close` in all terminal paths.

---

### M-03 · `handleError()` Saves Audit Fire-and-Forget
**File**: `execution-engine/.../api/ExecutionServiceImpl.java:270`  
**Status**: Persists  
**Fix**: Chain response send inside `.subscribe(v -> { onNext; onCompleted; }, err -> logger.error(...))`.

---

### M-06 · `_evaluate_exit_conditions()` Ignores Position Direction in Value Calculation
**File**: `src/monitor.py:451`  
**Status**: Persists  
**Fix**: `pnl += (exit_p - entry) * qty if side == "BUY" else (entry - exit_p) * qty`.

---

### M-07 · `place_market_order()` Bypasses `requests.Session` Connection Pool
**File**: `src/services/brokerage_service.py:141`  
**Status**: Persists  
**Fix**: Replace `requests.post(url, headers=self.headers, ...)` with `self.session.post(url, json=payload, timeout=15)`.

---

### M-08 · No Null Guard on Kalman Filter Return in `process_pair()`
**File**: `src/monitor.py:167-168`  
**Status**: Persists  
**Fix**: `if kf is None: return diagnostic` immediately after `get_or_create_filter`.

---

### M-09 · `RedisOrderSync.markInFlight()` Has No TTL
**File**: `execution-engine/.../persistence/RedisOrderSync.java:20-27`  
**Status**: Persists  
**Fix**: Add `.then(commands.expire(key, 3600L))` after `hset`.

---

### M-10 · `check_clock_sync()` Return Value Never Acted Upon
**File**: `src/utils.py`; `src/monitor.py`  
**Status**: Persists  
**Fix**: Call during startup; alert/raise if `False`.

---

### T-02 · `REGION` Config Variable Undefined — EU Hedging Always Falls Back to US
**File**: `src/services/risk_service.py:127`  
**Status**: New  
**Problem**: `region = getattr(settings, 'REGION', 'US')` — `REGION` is not in `config.py` or `.env.template`. EU regulatory hedge path (XSPS.L, SQQQ.L, R2SC.L) is never reachable even for EU deployments.  
**Fix**: Add `REGION: str = Field(default="US", ...)` to `Settings` and document in `.env.template`.

---

### A-04 · `asyncio.get_event_loop()` Used Inside Running Async Context
**File**: `src/daemons/sec_fundamental_worker.py:41, 90, 101`; `src/services/notification_service.py:260`; `src/services/data_service.py:146`  
**Status**: New  
**Problem**: `asyncio.get_event_loop()` called from within coroutines or async callbacks. Deprecated since Python 3.10, raises `DeprecationWarning` now and `RuntimeError` in Python 3.12+.  
**Fix**: Replace all instances with `asyncio.get_running_loop()`.

---

### J-04 · `getLegsList()` Not Validated — Silent Null-Field Audit Rows
**File**: `execution-engine/.../api/ExecutionServiceImpl.java:100`  
**Status**: New  
**Problem**: `request.getLegsList()` can be empty or contain null elements. Empty list = no audit rows written (trade appears unexecuted). Null element = NPE on `.getSide()` / `.getQuantity()`.  
**Fix**: Add guard `if (request.getLegsCount() == 0) { handleError(...); return; }` before the loop.

---

### S-04 · Unbounded WebSocket Connection List — Memory Exhaustion
**File**: `src/services/dashboard_service.py:19-43`  
**Status**: New  
**Problem**: `ConnectionManager.active_connections` is an unbounded list. A malicious (or buggy) client can open thousands of WebSocket connections to exhaust memory with no per-IP throttling or max-connection cap.  
**Fix**: Cap at a configurable `MAX_WS_CONNECTIONS` (e.g. 50); reject new connections over the limit with HTTP 429.

---

### S-05 · Docker Healthcheck Probes Possibly Non-Existent `/sse` Endpoint
**File**: `docker-compose.backend.yml:78`  
**Status**: New  
**Problem**: Healthcheck `curl http://localhost:8000/sse` — FastMCP may expose the SSE transport under a different path (`/messages`, `/events`). If the route doesn't exist the healthcheck always fails, the container is marked unhealthy, and Docker may restart it in a loop.  
**Fix**: Probe a known-stable endpoint like `/health` and add a `GET /health` route to the FastAPI app.

---

### S-06 · No Version Pinning in `requirements.txt` — Supply Chain Risk
**File**: `requirements.txt`  
**Status**: New  
**Problem**: No package is pinned to a specific version (`fastmcp`, `requests`, `yfinance`, `langgraph`, etc. all unpinned). A silent upstream update can break runtime behaviour or introduce a CVE.  
**Fix**: Run `pip freeze > requirements.lock` and use that in Docker; keep `requirements.txt` as human-readable loose spec.

---

## Low — Logic Gaps & Code Quality

### L-01 · `print()` Used Throughout Agents and Services
**File**: `src/agents/orchestrator.py:115,123,132,136,142,146,165`; `src/agents/fundamental_analyst.py:31,36`; `src/services/risk_service.py:161`  
**Status**: Persists (expanded scope)  
**Fix**: Replace all `print(...)` with `logger.warning/error(...)` using the module-level logger.

---

### L-02 · DRIP Tests Broken — `async def` Called Without `await`
**File**: `tests/unit/test_drip_safety.py:22, 35, 47`  
**Status**: Persists  
**Fix**: `IsolatedAsyncioTestCase` + `await`.

---

### L-03 · Cache Tests Broken — `async def` Called Without `await`
**File**: `tests/integration/test_brokerage_cache.py:28, 47, 72`  
**Status**: Persists  
**Fix**: `IsolatedAsyncioTestCase` + `await`.

---

### L-05 · Partial Fill State Not Tracked
**File**: `src/services/brokerage_service.py`  
**Status**: Persists  
**Fix**: Poll `/equity/orders/{id}` post-placement and update `quantity` from `filledQuantity`.

---

### L-06 · Corporate Action Invalidation Not Implemented
**File**: `src/services/arbitrage_service.py`  
**Status**: Persists  
**Fix**: Daily job to flush Kalman state for split/dividend-affected pairs.

---

### T-03 · Decimal Rounding Can Silently Produce Zero-Quantity Orders
**File**: `src/services/brokerage_service.py:108-110`  
**Status**: New  
**Problem**: `final_qty_dec = (decimal_qty / qty_incr).quantize(...) * qty_incr`. If `quantity < qty_incr / 2`, the result rounds to `0.0`. No post-rounding zero check — broker receives a zero-quantity order and rejects it, returning an error with no explicit warning that the allocation was too small.  
**Fix**: After rounding, add `if final_qty == 0: return {"status": "error", "message": f"Quantity rounds to zero for {ticker}"}`.

---

### J-05 · Unused Variable `statusForAudit` in `ExecutionServiceImpl`
**File**: `execution-engine/.../api/ExecutionServiceImpl.java:171`  
**Status**: New  
**Problem**: `final ExecutionStatus statusForAudit = failedStatus;` is assigned but never used — dead code from incomplete refactoring.  
**Fix**: Remove the declaration or wire it into the audit call.

---

## Open Bug Summary Table

| ID | File | Sev | Status | Description |
|----|------|-----|--------|-------------|
| C-02 | `brokerage_service.py:151` | Crit | Persists | `async _recover_timeout_order` called without `await` |
| T-01 | `risk_service.py:146` | Crit | **New** | Missing `await` on `get_portfolio()` → DEFCON-1 never fires |
| A-01 | `cash_management_service.py:20,46` | Crit | **New** | Missing `await` on async calls in cash management service |
| S-01 | `config.py:37` | Crit | **New** | Hardcoded default DB password "bot_pass" |
| S-02 | `dashboard_service.py:118` | Crit | **New** | Hardcoded default dashboard token "arbi-elite-2026" |
| H-01 | `brokerage_service.py:120` | High | Persists | New UUID per retry breaks idempotency |
| H-03 | `brokerage_service.py:141,194,262` | High | Persists | Sync blocking calls stall event loop (3 sites) |
| H-05 | `monitor.py:190` | High | Persists | Missing `sector` key → all pairs check NVDA |
| A-03 | `monitor.py:184,213` | High | **New** | Race condition on `self.active_signals` under `asyncio.gather` |
| S-03 | `dashboard_service.py:114` | High | **New** | DEV_MODE bypasses all dashboard auth |
| S-07 | `monitor.py:221,481` | High | **New** | Zero test coverage for execute_trade / _close_position / orchestrator veto |
| S-08 | `test_brokerage.py:50` | High | **New** | `get_portfolio()` called without `await` in sync test |
| J-01 | `ExecutionServiceImpl.java:105` | High | **New** | L2OrderBook not null-checked → NPE in VwapCalculator |
| J-02 | `ExecutionServiceImpl.java:185` | High | **New** | `.block()` in gRPC handler thread exhausts thread pool |
| J-03 | `ExecutionServiceImpl.java:176` | High | **New** | Double `onCompleted()` violates gRPC contract |
| M-01 | `TradeLedgerRepository.java:72` | Med | Persists | `getStatus()` never closes DB connection |
| M-02 | `TradeLedgerRepository.java:67` | Med | Persists | `saveAudits()` leaks connection on error rollback |
| M-03 | `ExecutionServiceImpl.java:270` | Med | Persists | Error path audit saved fire-and-forget |
| M-06 | `monitor.py:451` | Med | Persists | Exit condition ignores position direction |
| M-07 | `brokerage_service.py:141` | Med | Persists | `place_market_order` uses module-level `requests.post` |
| M-08 | `monitor.py:167` | Med | Persists | No null guard on Kalman filter in `process_pair()` |
| M-09 | `RedisOrderSync.java:20` | Med | Persists | `markInFlight()` has no TTL |
| M-10 | `utils.py` | Med | Persists | `check_clock_sync()` result never enforced |
| T-02 | `risk_service.py:127` | Med | **New** | `REGION` config undefined → EU hedge path unreachable |
| A-04 | `sec_fundamental_worker.py:41,90,101` | Med | **New** | `asyncio.get_event_loop()` deprecated → fails Python 3.12+ |
| J-04 | `ExecutionServiceImpl.java:100` | Med | **New** | `getLegsList()` not validated → silent null-field rows |
| S-04 | `dashboard_service.py:19` | Med | **New** | Unbounded WebSocket connection list |
| S-05 | `docker-compose.backend.yml:78` | Med | **New** | Healthcheck probes `/sse` — may not exist |
| S-06 | `requirements.txt` | Med | **New** | No version pinning — supply chain risk |
| L-01 | `orchestrator.py`, `fundamental_analyst.py`, `risk_service.py` | Low | Persists | `print()` bypasses logger |
| L-02 | `test_drip_safety.py:22` | Low | Persists | DRIP tests broken — no await |
| L-03 | `test_brokerage_cache.py:28` | Low | Persists | Cache tests broken — no await |
| L-05 | `brokerage_service.py` | Low | Persists | Partial fills not tracked |
| L-06 | `arbitrage_service.py` | Low | Persists | Corporate action invalidation not implemented |
| T-03 | `brokerage_service.py:108` | Low | **New** | Decimal rounding can produce zero-quantity order silently |
| J-05 | `ExecutionServiceImpl.java:171` | Low | **New** | Unused variable `statusForAudit` |

---

## Confirmed Fixed

| ID | Description | Evidence |
|----|-------------|---------|
| C-01 | `pd` not imported in `monitor.py` | `import pandas as pd` at line 3 |
| H-02 | `execute_order()` missing `await` | `return await self.place_value_order(...)` |
| H-04 Sprint H | Beacon regime dict vs string | `regime_data.get("regime", "NEUTRAL")` at line 267 |
| H-04 Phase 0 | Same in Phase 0 block | `regime_data.get("regime", "NEUTRAL")` at line 70 |
| M-04 | PnL hardcoded `0.0` | Per-leg directional calculation in `_close_position` |
| M-05 | Journal before broker execution | Moved after both legs return |
| M-11 | `get_portfolio`/`get_pending_orders` block event loop | `asyncio.to_thread(self.session.get, ...)` |
| L-01 (data_service) | `print()` in data_service | `logger.error(...)` |
| L-04 | Slippage tests broken | `IsolatedAsyncioTestCase` + `AsyncMock` |
| L-07 | 1 ms latency alarm fires constantly | Default raised to 10 ms |
| C-01 prev | `mean: 0.0` in spread metrics | Returns `intercept` |
| M-12 prev | OLS missing `add_constant()` | `sm.add_constant(s2)` |
| M-13 prev | Tick size float arithmetic | `decimal.Decimal` quantisation |
| M-14 prev | No rate-limit cache | 5 s TTL + async lock |
| L-02 prev | Bid-ask additive formula | `(1+a)*(1+b)-1` |
| L-03 prev | Full portfolio as amount | `total_cash * 0.05` |
| L-08 prev | UCITS hedge mappings missing | `EU_HEDGE_MAPPINGS` added |
| L-12 prev | No flash-crash limit price | `price * 1.01 / 0.99` |
