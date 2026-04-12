# Bug & Error Register (Revised — 2026-04-12)

Audit against current source code. Previously reported bugs that are confirmed fixed are listed at the bottom. Severity: **Critical** → **High** → **Medium** → **Low**.

---

## Critical — System-Breaking

### C-01 · `pd` Used Without Import in `initialize_pairs()`
**File**: `src/monitor.py` line 125  
**Status**: ~~Fixed~~  
**Problem**: `numpy` is imported inline (`import numpy as np`), but `pd.isna(hedge)` is called on the same line using `pd` (pandas), which is never imported anywhere in `monitor.py`. Every startup raises `NameError: name 'pd' is not defined`, crashing the entire boot sequence before a single pair is initialized.  
**Fix**: Add `import pandas as pd` to the top-level imports of `monitor.py`.

---

### C-02 · `_recover_timeout_order()` Is `async def` Called Without `await` in a Sync Function
**File**: `src/services/brokerage_service.py` line 151  
**Status**: **Persists**  
**Problem**: `place_market_order()` is a plain `def` (synchronous). On a `requests.Timeout`, it executes `return self._recover_timeout_order(client_order_id, ticker)`. But `_recover_timeout_order` is declared `async def`. Calling an async function without `await` returns a bare coroutine — it is never scheduled, never run. The caller `place_value_order()` then calls `result.get("status")` on this coroutine and raises `AttributeError: 'coroutine' object has no attribute 'get'`. Every network timeout on an order crashes with the wrong error and the order status is never recovered.  
**Fix**: Either make `place_market_order()` async (and await the call), or run recovery with `asyncio.get_event_loop().run_until_complete(...)` from the sync context.

---

## High — Execution Correctness & Capital Safety

### H-01 · Idempotency Key Is Not Stable Across Retries
**File**: `src/services/brokerage_service.py` line 120  
**Status**: **Persists**  
**Problem**: A fresh `uuid.uuid4()` is generated on every call to `place_market_order()`. If a network timeout fires (C-02) or the caller retries, a brand-new `clientOrderId` is sent to the broker. The broker sees it as a distinct order and the same trade is placed twice.  
**Fix**: Derive `clientOrderId` deterministically from `signal_id` using a UUIDv5 namespace hash so retries produce the same key.

---

### H-02 · `execute_order()` Calls `place_value_order()` Without `await`
**File**: `src/services/brokerage_service.py` line 172  
**Status**: **Persists**  
**Problem**: `execute_order()` is `async def` and `place_value_order()` is also `async def`. The call is `return self.place_value_order(ticker, amount_fiat, side)` with no `await`. This returns the coroutine unawaited — DCA and goal-based order paths never execute any trades. They silently return a coroutine object.  
**Fix**: Change to `return await self.place_value_order(...)`.

---

### H-03 · Blocking `requests` Calls Stall the Async Event Loop
**File**: `src/services/brokerage_service.py` lines 141, 262, 194  
**Status**: **Persists**  
**Problem**: Multiple blocking `requests` / `session.get()` calls run directly on the asyncio event loop:
- `place_market_order()` (sync) calls `requests.post(url, ...)` — blocking TCP for up to 15 s.
- `place_value_order()` (async) calls `self.place_market_order(...)` directly without `asyncio.to_thread`.
- `check_dividends_and_reinvest()` (async) calls `self.get_account_cash()` directly (blocking up to 3 × 10 s with retries).

All three stall the entire event loop — every pair scan, Kalman update, and dashboard SSE feed — for the duration of the HTTP request.  
**Fix**: Wrap each sync call in `await asyncio.to_thread(...)`, or switch to `httpx` with async client.

---

### H-04 · Sprint-H Beacon Regime Check Compares Dict to String — VETO Never Fires
**File**: `src/agents/orchestrator.py` lines 266–267  
**Status**: **Persists** *(Phase 0 check at line 70 was fixed; Sprint H block was not)*  
**Problem**: The Sprint H "Sector Gravity Check" loop does:
```python
regime = await macro_economic_agent.get_ticker_regime(beacon)
if regime == "EXTREME_VOLATILITY":
```
`get_ticker_regime()` returns a **dict** (`{"regime": ..., "confidence": ...}`). Comparing a dict to the string `"EXTREME_VOLATILITY"` is always `False`. The per-ticker flash-crash VETO for individual beacons (NVDA, JPM, XOM, KO) **never triggers** even during a crash. Capital is not protected.  
**Fix**: Change to `regime_data = await macro_economic_agent.get_ticker_regime(beacon)` and check `regime_data.get("regime") == "EXTREME_VOLATILITY"`.

---

### H-05 · All Pair Sectors Default to `Technology` — Wrong Beacon for Every Non-Tech Pair
**File**: `src/agents/orchestrator.py` line 66; `src/monitor.py` lines 189–193  
**Status**: **Persists**  
**Problem**: Phase 0 extracts `sector = state['signal_context'].get('sector', 'Technology')`. The signal context built in `monitor.py` never includes a `'sector'` key. Every pair — including financials (JPM/BAC), energy (XOM/CVX), and consumer (KO/PEP) — always falls into `'Technology'` and checks NVDA. A financial crash that leaves NVDA unaffected will not block financial-pair trades.  
**Fix**: Add `"sector": settings.PAIR_SECTORS.get(pair_id, "Technology")` to the `signal_context` dict in `monitor.py`.

---

## Medium — Data Integrity & Reliability

### M-01 · `TradeLedgerRepository.getStatus()` Leaks Database Connections
**File**: `execution-engine/src/main/java/com/arbitrage/engine/persistence/TradeLedgerRepository.java` lines 72–79  
**Status**: **Persists**  
**Problem**: `getStatus()` opens a connection via `connectionFactory.create()` but never calls `connection.close()`. Each call permanently consumes one connection from the R2DBC pool. Under any load the pool exhausts and subsequent queries block indefinitely.  
**Fix**: Chain `.doFinally(signal -> connection.close())` after the query, or restructure using `Flux.usingWhen()` to guarantee cleanup.

---

### M-02 · `TradeLedgerRepository.saveAudits()` Leaks Connection on Error Rollback
**File**: `execution-engine/src/main/java/com/arbitrage/engine/persistence/TradeLedgerRepository.java` lines 66–68  
**Status**: **Persists**  
**Problem**: The reactive chain is:
```java
.then(Mono.from(connection.commitTransaction()))
.onErrorResume(e -> Mono.from(connection.rollbackTransaction()).then(Mono.error(e)))
.then(Mono.from(connection.close()))
```
`connection.close()` is only reached on the success path. After an error, `onErrorResume` rolls back and re-throws; the `.then(connection.close())` is skipped. Every failed trade audit permanently leaks a connection.  
**Fix**: Replace with `Mono.usingWhen(connectionFactory.create(), conn -> ..., Connection::close, (conn, err) -> conn.close(), conn -> conn.close())`.

---

### M-03 · `handleError()` in `ExecutionServiceImpl` Saves Audit Fire-and-Forget
**File**: `execution-engine/src/main/java/com/arbitrage/engine/api/ExecutionServiceImpl.java` line 270  
**Status**: **Persists**  
**Problem**: `repository.saveAudits(...).subscribe()` is called with no completion or error callback. The gRPC response is sent immediately after (lines 272–273) before the audit write has even started. On a slow DB the audit is silently lost — the caller already received a response with no indication.  
**Fix**: Chain the response send inside the reactive completion: `.subscribe(v -> { responseObserver.onNext(...); responseObserver.onCompleted(); }, err -> logger.error(...))`.

---

### M-04 · PnL Hardcoded to `0.0` in `_close_position()`
**File**: `src/monitor.py` line 494  
**Status**: **Persists**  
**Problem**: Every position closure logs `pnl = 0.0`. `persistence_service.get_total_pnl()` will always return approximately zero regardless of actual performance. Circuit breakers, Sortino calculations, and downstream analytics are all fed incorrect data.  
**Fix**: Compute PnL from entry price vs exit price using the leg cost basis stored at entry, or fetch fill prices from the broker after order confirmation.

---

### M-05 · `execute_trade()` Logs Trade Journal Before Broker Execution
**File**: `src/monitor.py` lines 267–276 vs 296–301  
**Status**: **Persists**  
**Problem**: `persistence_service.log_trade_journal(...)` is called before any broker order is placed. If leg A succeeds but leg B fails, the journal already records a complete entry for both legs. On restart, the system sees a journal entry for a signal it never fully executed, potentially triggering incorrect exit logic.  
**Fix**: Write the journal entry only after both legs have confirmed non-error broker responses.

---

### M-06 · `_evaluate_exit_conditions()` Ignores Position Direction in Value Calculation
**File**: `src/monitor.py` line 451  
**Status**: **Persists**  
**Problem**: `current_value = (leg_a["quantity"] * p_a) + (leg_b["quantity"] * p_b)` adds both leg values regardless of direction. In a pair trade one leg is short — its contribution to net value is negative. The formula computes gross notional, not net P&L. The kill-switch threshold (`max_loss_pct=0.02`) fires based on total position size instead of actual loss.  
**Fix**: Sign each leg's contribution based on its `side` field: `+qty * price` for BUY, `-qty * price` for SELL.

---

### M-07 · `place_market_order()` Bypasses `requests.Session` Connection Pool
**File**: `src/services/brokerage_service.py` line 141  
**Status**: **Persists**  
**Problem**: `place_market_order()` calls the module-level `requests.post(url, headers=self.headers, ...)` instead of `self.session.post(...)`. This creates a new TCP connection per order, bypasses the session's connection pool, and re-encodes the auth header on every call.  
**Fix**: Replace with `self.session.post(url, json=payload, timeout=15)`.

---

### M-08 · No Null Guard on Kalman Filter Return in `process_pair()`
**File**: `src/monitor.py` lines 167–168  
**Status**: **Persists**  
**Problem**: `kf = await arbitrage_service.get_or_create_filter(pair['id'])` has no null check. The very next line calls `kf.update(price_a, price_b)`, raising `AttributeError: 'NoneType'` if Redis is unreachable and the in-memory cache is empty. The outer `except Exception` swallows this, masking the Redis outage as a generic pair error.  
*(Note: a null guard does exist in `_evaluate_exit_conditions()` line 462 — just not in `process_pair()`.)*  
**Fix**: Add `if kf is None: return diagnostic` immediately after the `get_or_create_filter` call.

---

### M-09 · `RedisOrderSync.markInFlight()` Has No TTL
**File**: `execution-engine/src/main/java/com/arbitrage/engine/persistence/RedisOrderSync.java` lines 20–27  
**Status**: **Persists**  
**Problem**: `markInFlight()` uses plain `HSET` with no `EXPIRE`. Keys persist forever, eventually exhausting memory and permanently blocking order slots for recycled signal IDs.  
**Fix**: Add `.then(commands.expire(key, 3600L))` after the `hset` call, or ensure `markInFlight()` is never called outside the `checkAndMarkInFlight()` Lua path.

---

### M-10 · `check_clock_sync()` Return Value Is Never Acted Upon
**File**: `src/utils.py` lines 9–43; `src/monitor.py`  
**Status**: **Persists**  
**Problem**: `check_clock_sync()` is defined and importable but never called in `monitor.py`. Clock drift above 100 µs is never detected or alerted. Latency budget calculations become silently invalid.  
**Fix**: Call `check_clock_sync()` during startup health checks in `run()`; raise or send an alert if it returns `False`.

---

### M-11 · `get_portfolio()` and `get_pending_orders()` Block Event Loop Inside Async Lock
**File**: `src/services/brokerage_service.py` lines 320, 347  
**Status**: **New**  
**Problem**: Both methods are `async def` and acquire `self._cache_lock` with `async with`. But inside the lock they call `self.session.get(...)` — a blocking synchronous HTTP call. The event loop is frozen for the duration of the HTTP request (up to 10 s timeout) while the lock is held. Any concurrent coroutine that also needs the lock (e.g. a dashboard health-check hitting `get_portfolio()` while a signal scan runs) will deadlock until the HTTP call resolves.  
**Fix**: Wrap the `self.session.get(...)` call in `await asyncio.to_thread(self.session.get, url, ...)` inside the lock, or switch to `httpx.AsyncClient`.

---

## Low — Logic Gaps & Code Quality

### L-01 · `print()` Used Throughout Agents and Data Layer
**File**: `src/agents/orchestrator.py` lines 115, 123, 132; `src/agents/fundamental_analyst.py` lines 31, 36; `src/services/data_service.py` lines 40, 71  
**Status**: **Persists + expanded scope**  
**Problem**: Agent failures, circuit breaker trips, fundamental cache misses, LLM errors, and yfinance fetch errors are all reported via `print()`. This bypasses log routing, log levels, structured formatters, and any aggregation pipeline (CloudWatch, Datadog). Scope was previously only orchestrator and fundamental_analyst; data_service has the same pattern.  
**Fix**: Replace all `print(...)` with `logger.warning(...)` or `logger.error(...)` using the module-level logger.

---

### L-02 · DRIP Tests Are Broken — `check_dividends_and_reinvest()` Is `async def` Called Without `await`
**File**: `tests/unit/test_drip_safety.py` lines 22, 35, 47  
**Status**: **Persists**  
**Problem**: All three DRIP tests call `self.service.check_dividends_and_reinvest()` without `await` in a sync `unittest.TestCase`. Each call returns an unawaited coroutine; `mock_place.assert_called_with(...)` always fails because the function body never ran.  
**Fix**: Convert tests to `async` using `unittest.IsolatedAsyncioTestCase` and add `await` to each call.

---

### L-03 · Cache Tests Are Broken — `get_portfolio()` and `get_pending_orders()` Are `async def` Called Without `await`
**File**: `tests/integration/test_brokerage_cache.py` lines 28, 33, 47, 52, 72, 78, 83  
**Status**: **Persists**  
**Problem**: All calls to `self.service.get_portfolio()` and `self.service.get_pending_orders()` are made without `await` in sync tests. Each returns a coroutine; `assertEqual(len(res1), 1)` raises `TypeError: object of type 'coroutine' has no len()`.  
**Fix**: Convert to async tests using `IsolatedAsyncioTestCase`.

---

### L-04 · Slippage Guard Tests Are Broken — `place_value_order()` Is `async def` Called Without `await`
**File**: `tests/unit/test_slippage_guard.py` lines 22, 39  
**Status**: **New**  
**Problem**: Both slippage guard tests call `self.service.place_value_order("AAPL", 100.0, "BUY/SELL")` without `await` in a sync `unittest.TestCase`. The method is `async def`, so the call returns an unawaited coroutine; `place_market_order` never runs. Additionally, `mock_price` is a plain `MagicMock` patching an `async def` (`data_service.get_latest_price`), so when `place_value_order` does `await data_service.get_latest_price([ticker])` it awaits a `MagicMock()` and raises `TypeError: object MagicMock can't be used in 'await' expression`. Both tests give false results.  
**Fix**: Convert tests to `IsolatedAsyncioTestCase`, add `await` to `place_value_order` calls, and replace `mock_price` with `AsyncMock(return_value={"AAPL": 100.0})`.

---

### L-05 · Partial Fill State Not Tracked
**File**: `src/services/brokerage_service.py`  
**Status**: **Persists**  
**Problem**: All orders are assumed to fill fully and immediately. Partial fills result in one leg being over-hedged or under-hedged, creating unintended directional exposure.  
**Fix**: After placing each order, poll `/equity/orders/{id}` and update stored quantity from `filledQuantity` in the response.

---

### L-06 · Corporate Action Invalidation Not Implemented
**File**: `src/services/arbitrage_service.py`  
**Status**: **Persists**  
**Problem**: No daily calendar check for splits or dividends. A stock split resets the price series; the cached Kalman state trained on pre-split prices becomes invalid and generates bad signals until slow reconvergence.  
**Fix**: Implement a daily job that fetches corporate action events and clears the Kalman state for affected pairs from both in-memory dict and Redis.

---

## Summary Table

| ID | File | Severity | Status | Description |
|----|------|----------|--------|-------------|
| C-01 | `monitor.py:125` | Critical | **Fixed** | `pd` used without import → `NameError` on every boot |
| C-02 | `brokerage_service.py:151` | Critical | Persists | `async def _recover_timeout_order` called without `await` → coroutine on timeout |
| H-01 | `brokerage_service.py:120` | High | Persists | New UUID per retry breaks idempotency |
| H-02 | `brokerage_service.py:172` | High | **Fixed** | `execute_order()` missing `await` on `place_value_order()` |
| H-03 | `brokerage_service.py:141,262,194` | High | Persists | Sync blocking calls stall async event loop (3 call sites) |
| H-04 | `orchestrator.py:266` | High | **Fixed** | Sprint H beacon regime dict compared to string → flash-crash VETO never fires |
| H-05 | `orchestrator.py:66` | High | Persists | Missing `sector` key → all pairs check NVDA regardless of sector |
| M-01 | `TradeLedgerRepository.java:72` | Medium | Persists | `getStatus()` never closes DB connection → pool exhaustion |
| M-02 | `TradeLedgerRepository.java:67` | Medium | Persists | `saveAudits()` doesn't close connection on error rollback |
| M-03 | `ExecutionServiceImpl.java:270` | Medium | Persists | Error path audit saved fire-and-forget |
| M-04 | `monitor.py:494` | Medium | **Fixed** | PnL hardcoded to `0.0` → all PnL reporting broken |
| M-05 | `monitor.py:267` | Medium | **Fixed** | Trade journal logged before broker confirmation |
| M-06 | `monitor.py:451` | Medium | Persists | Exit condition value ignores position direction |
| M-07 | `brokerage_service.py:141` | Medium | Persists | `place_market_order` uses module-level `requests.post` instead of session |
| M-08 | `monitor.py:167` | Medium | Persists | No null guard on Kalman filter return in `process_pair()` |
| M-09 | `RedisOrderSync.java:20` | Medium | Persists | `markInFlight()` has no TTL → infinite key lifespan |
| M-10 | `utils.py` / `monitor.py` | Medium | Persists | `check_clock_sync()` result never enforced |
| M-11 | `brokerage_service.py:320,347` | Medium | **Fixed** | `get_portfolio`/`get_pending_orders` block event loop inside async lock |
| L-01 | `orchestrator.py`, `fundamental_analyst.py`, `data_service.py` | Low | Partial (data_service fixed) | `print()` bypasses logger — data_service resolved; orchestrator/fundamental_analyst remain |
| L-02 | `test_drip_safety.py:22,35,47` | Low | Persists | DRIP tests broken — async method called without `await` |
| L-03 | `test_brokerage_cache.py:28,47,72` | Low | Persists | Cache tests broken — async methods called without `await` |
| L-04 | `test_slippage_guard.py:22,39` | Low | **Fixed** | Slippage tests broken — async `place_value_order` called without `await`; mock not `AsyncMock` |
| L-05 | `brokerage_service.py` | Low | Persists | Partial fills not tracked |
| L-06 | `arbitrage_service.py` | Low | Persists | Corporate action invalidation not implemented |

---

## Confirmed Fixed

| ID | Description | Evidence |
|----|-------------|---------|
| L-07 (old) | `LATENCY_ALARM_THRESHOLD_MS = 1.0` fires constantly | `config.py` now defaults to `10.0` with comment "Bug M-11: Increased threshold to 10ms" |
| H-04 Phase 0 | Phase 0 macro regime check compared dict to string | `orchestrator.py:69-72` now uses `regime_data.get("regime", "NEUTRAL")` correctly *(Sprint H block at line 266 remains broken — see H-04 above)* |
| C-01 (prev) | `mean: 0.0` hardcoded in `get_spread_metrics()` | Now returns `intercept` |
| C-02 (prev) | Missing `import uuid` in `brokerage_service.py` | Import present |
| C-03 (prev) | `TradeLedgerRepository` batch-bind loop | R2DBC `.add()` pattern now correct |
| H-02 (prev) | `place_value_order` blocking sync calls | Now `async def` with `await` |
| H-03 (prev) | DRIP stale cash balance | Re-fetched per leg |
| H-04 (prev) | `process_pair()` always returned `None` | Returns `diagnostic` dict |
| M-01 (prev) | Look-ahead bias in `get_spread_metrics()` | `iloc[:-1]` applied |
| M-02 (prev) | Kalman NaN/Inf check ran after state committed | Guard runs before assignment |
| M-03 (prev) | `threading.Lock` in async context | Replaced with `asyncio.Lock()` |
| M-05 (prev) | `get_latest_price()` called without `await` | `await` added |
| M-06 (prev) | Circuit breaker counter never incremented | Persisted via `persistence_service` |
| M-07 (prev) | `ExecutionServiceImpl` reactive chain race | Proper `flatMap` chain |
| M-09 (prev) | `SlippageGuard` no null validation | Explicit null check added |
| M-10 (prev) | Market hours not enforced | `is_market_open()` check added |
| M-12 (prev) | OLS regression missing `add_constant()` | `sm.add_constant(s2)` added |
| M-13 (prev) | Tick size float arithmetic | `decimal.Decimal` quantisation applied |
| M-14 (prev) | No rate-limit cache on `/portfolio` and `/orders` | 5 s TTL + async lock cache added |
| L-01 (prev) | Non-finite hedge ratio passed to Kalman init | Guarded with `np.isinf` check |
| L-02 (prev) | Bid-ask spread additive formula | Replaced with `(1+a)*(1+b)-1` |
| L-03 (prev) | Full portfolio as `amount_fiat` | Now passes `total_cash * 0.05` per pair |
| L-07 (prev) | LLM JSON parse no markdown-fence fallback | `extract_json()` in `utils.py` |
| L-08 (prev) | UCITS hedge mappings missing | `EU_HEDGE_MAPPINGS` added |
| L-12 (prev) | No flash-crash limit price | `limit_price = price * 1.01/0.99` in `place_value_order` |
