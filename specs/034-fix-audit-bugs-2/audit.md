# Audit 034 — Bug Report (2026-04-12)

9 real runtime bugs found after merging 033-fix-audit-bugs.

---

## BUG-1 · CRITICAL · Missing `await` on `get_portfolio()`
**File:** `src/services/notification_service.py:148`
**Bug:** `portfolio = brokerage.get_portfolio()` — `get_portfolio()` is async but called without `await`.
**Impact:** `portfolio` is a Coroutine object; iteration at line 149 raises `TypeError`. The `/cash` Telegram command crashes every time.
**Fix:** `portfolio = await brokerage.get_portfolio()`

---

## BUG-2 · CRITICAL · Missing `await` on `place_value_order()`
**File:** `src/services/notification_service.py:126`
**Bug:** `result = brokerage.place_value_order(ticker, amount, "BUY")` — async method called without `await`.
**Impact:** `result` is a Coroutine; `.get()` at line 128 raises `AttributeError`. The `/invest` Telegram command crashes.
**Fix:** `result = await brokerage.place_value_order(ticker, amount, "BUY")`

---

## BUG-3 · HIGH · Blocking sync call inside async loop (event loop stall)
**File:** `src/services/brokerage_service.py` — `check_dividends_and_reinvest()` loop
**Bug:** `get_account_cash()` is a synchronous HTTP call invoked directly inside an async method, blocking the event loop on every DRIP cycle.
**Impact:** The entire async event loop stalls during the HTTP request. All concurrent tasks (monitor, risk checks, heartbeats) are frozen.
**Fix:** `available_cash = await asyncio.to_thread(self.get_account_cash)`

---

## BUG-4 · HIGH · Fire-and-forget `create_task` swallows exceptions silently
**File:** `src/services/persistence_service.py:286` (approx.)
**Bug:** `asyncio.create_task(reflection_agent.reflect_on_trade(...))` — no reference kept, no done-callback.
**Impact:** Any exception inside the reflection task is silently swallowed with only a generic "unhandled exception in task" log. Failures are invisible.
**Fix:**
```python
task = asyncio.create_task(reflection_agent.reflect_on_trade(str(signal_id)))
task.add_done_callback(
    lambda t: logger.error("Reflection task failed: %s", t.exception())
    if not t.cancelled() and t.exception() else None
)
```

---

## BUG-5 · CRITICAL · Non-idempotent order ID — duplicate trades on retry
**File:** `src/services/brokerage_service.py:120` (approx.)
**Bug:** `client_order_id = str(uuid.uuid4())` generated fresh on every call to `place_market_order()`.
**Impact:** If the first call succeeds but the network times out before the response arrives, a retry generates a NEW order ID and submits a second order. Results in double-fill / double-trading.
**Fix:** Accept `client_order_id: str = None` as a parameter. Generate the UUID at the **call site** before any retry loop, and pass it through on all retry attempts.

---

## BUG-6 · CRITICAL · Unhandled `None` from `classify_current_regime()` crashes trade path
**File:** `src/monitor.py:270` and `src/monitor.py:302`
**Bug:** `regime_info = await market_regime_service.classify_current_regime(t_a)` — if the service is unavailable or returns `None`, `regime_info["regime"]` at line 302 raises `TypeError: 'NoneType' object is not subscriptable`.
**Impact:** Any trade opportunity where regime classification fails causes a crash mid-execution. The pair is skipped and the error propagates up.
**Fix:**
```python
regime_info = await market_regime_service.classify_current_regime(t_a)
if not regime_info:
    logger.warning("Regime unavailable for %s; defaulting to STABLE", t_a)
    regime_info = {"regime": "STABLE", "confidence": 0.5, "features": {}}
```

---

## BUG-7 · MEDIUM · Redis client never closed — connection leak on shutdown
**File:** `src/services/redis_service.py`
**Bug:** `redis.asyncio.Redis` instance is created at module level (singleton) with no teardown path. No `aclose()` is called when the application exits.
**Impact:** Graceful shutdown leaves the Redis connection dangling. On repeated restarts (e.g. Docker restart loops) this can exhaust the server's connection pool.
**Fix:** Add `async def close(self): await self.client.aclose()` and call it in `monitor.py`'s `finally` block.

---

## BUG-8 · MEDIUM · `spread_a` / `spread_b` redundant inner checks obscure actual logic
**File:** `src/monitor.py:233-234`
**Bug:** Inner `if bid_a > 0` checks are redundant (already guarded by outer condition at line 232). The issue is the fallback value is `0`, which would pass the `< 0.003` spread guard and allow a trade even when spread data is unavailable.
**Impact:** If the outer guard ever fails to catch a zero bid (e.g. due to a future refactor removing the check), a `0` spread would silently pass the spread filter, letting trades through with unknown transaction costs.
**Fix:** Remove the inner ternary; replace with a direct assertion or raise on bad data.

---

## BUG-9 · HIGH · `persistence_service.py` referenced but file does not exist on current branch
**File:** `src/services/persistence_service.py`
**Bug:** Multiple services import from `persistence_service`, but the file was deleted in the remote master merge. Any module that does `from src.services.persistence_service import ...` will raise `ModuleNotFoundError` at import time.
**Impact:** The entire application fails to start.
**Fix:** Verify all imports referencing `persistence_service` and either restore the file or redirect imports to the correct module.

---

## Summary Table

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | CRITICAL | notification_service.py:148 | Missing await on get_portfolio() |
| 2 | CRITICAL | notification_service.py:126 | Missing await on place_value_order() |
| 3 | HIGH | brokerage_service.py | Sync call blocks event loop in async DRIP |
| 4 | HIGH | persistence_service.py:~286 | create_task with no exception handling |
| 5 | CRITICAL | brokerage_service.py:~120 | Non-idempotent UUID per call → double trades |
| 6 | CRITICAL | monitor.py:270,302 | None regime_info crashes trade path |
| 7 | MEDIUM | redis_service.py | Redis connection never closed |
| 8 | MEDIUM | monitor.py:233-234 | Redundant spread guard inner checks |
| 9 | HIGH | persistence_service.py | File missing — ModuleNotFoundError on boot |
