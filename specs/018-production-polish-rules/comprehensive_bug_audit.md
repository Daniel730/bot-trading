# Ultimate Production Lapidation: Comprehensive Bug Audit & Remediation Plan

**Status:** REQUIRED BEFORE REAL-MONEY DEPLOYMENT
**Audience:** Senior Tech Team & QA Engineering
**Target:** `bot-trading` Microservices Architecture

---

## 1. Quantitative & Mathematical Vulnerabilities (Silent Killers)

### 1.1 Kalman Filter Covariance Explosion (`NaN` Propagation)

- **File:** `src/services/kalman_service.py` / `src/services/arbitrage_service.py`
- **Bug:** If the spread between two cointegrated assets becomes temporarily perfectly correlated or static, the Kalman filter's measurement noise covariance matrix ($R$) or estimate error covariance ($P$) can become singular or close to zero. Python's `numpy` will throw a `LinAlgError` or silently propagate `NaN` (Not a Number) values to the hedge ratio.
- **Impact:** The bot will attempt to calculate order sizes using `NaN`, causing immediate app crashes or sending malformed payloads to the broker.
- **Fix:** Implement a covariance guard. Before updating the state, check `np.isnan().any()` and `np.isinf().any()`. If detected, reset the filter to the `initial_state` or apply a ridge regression penalty (Tikhonov regularization) to the diagonal of the covariance matrix.

### 1.2 Unadjusted Corporate Actions (Splits/Dividends) in Historical Feed

- **File:** `src/services/data_service.py`
- **Bug:** Fetching raw historical prices without explicit adjustment flags. If a stock undergoes a 2:1 split, the price instantly halves.
- **Impact:** The Arbitrage OLS regression and Z-score calculations will perceive a 50% price drop as a massive 10-sigma statistical anomaly and will instantly max out margin trying to "buy the dip" on a spread that doesn't actually exist.
- **Fix:** Enforce `adjusted=True` on all historical data provider queries. Implement a daily check against a corporate actions calendar API; if a split is detected, invalidate and rebuild all cached Kalman filters for that ticker.

### 1.3 Look-Ahead Bias in Z-Score Normalization

- **File:** `src/services/arbitrage_service.py`
- **Bug:** Calculating the rolling Z-score using `(current_spread - spread.mean()) / spread.std()`. If `spread.mean()` is calculated over the _entire_ dataset rather than a strictly trailing window ending at $T-1$, future data leaks into the present decision.
- **Impact:** Backtests will look highly profitable, but live forward-testing will perform terribly.
- **Fix:** Ensure `.rolling(window=X).mean().shift(1)` is strictly used for baseline calculations.

---

## 2. Execution & Brokerage State Desyncs

### 2.1 The "Partial Fill" State Desync

- **File:** `src/services/brokerage_service.py`
- **Bug:** When tracking open positions, the bot assumes that if `place_market_order()` returns 200 OK, `executed_qty == requested_qty`. In reality, T212 might partially fill an order due to low liquidity, leaving the rest pending.
- **Impact:** The bot updates its internal state to reflect owning 100 shares, but it only owns 40. When it tries to close the position later, it sends a `SELL 100` order, which the broker rejects as "Insufficient Shares." The bot gets stuck holding the bag.
- **Fix:** Implement WebSockets or polling for explicit `Order Execution Reports`. Do not update internal portfolio state based on _requests_; only update it based on _broker confirmations/receipts_.

### 2.2 Network Drop / Idempotency Failure (Duplicate Execution)

- **File:** `src/services/brokerage_service.py`
- **Bug:** `requests.post(order_payload)` is sent. The broker executes the trade. But exactly at that millisecond, the Docker container loses network connectivity and receives a `TimeoutError`. The bot assumes the order failed and retries.
- **Impact:** The bot accidentally buys 2x or 3x the intended amount, violating risk limits.
- **Fix:** Implement Idempotency Keys (UUIDs). Append a unique `client_order_id` to every order payload. If a timeout occurs, query the broker's `/orders` endpoint by that UUID _before_ ever retrying the POST request.

### 2.3 Floating-Point Tick Size Violations

- **File:** `src/services/brokerage_service.py`
- **Bug:** Calculating limit orders as `price * 1.01`. If price is $1.05, `1.05 * 1.01 = 1.0605`. Trading 212 might require step sizes of `$0.01` for this tier.
- **Impact:** Broker rejects order with `INVALID_TICK_SIZE` or `DECIMAL_PLACES_EXCEEDED`.
- **Fix:** Fetch `tick_size` metadata for the asset. Use `decimal.Decimal` to round limit prices exactly to the allowed tick size (e.g., `math.floor(price / tick_size) * tick_size`).

---

## 3. AI Agents & Multi-Agent Orchestration

### 3.1 LLM Structured Output Hallucination

- **File:** `src/agents/*_agent.py` (Bull/Bear/Fundamental)
- **Bug:** Assuming `json.loads(response.text)` will always work. LLMs occasionally wrap JSON in markdown blocks (
  http://googleusercontent.com/immersive_entry_chip/0

### Next Steps for Implementation

If you want to assertively push these fixes using Spec-Kit, we can target them block by block. Which domain should we fix first? (e.g., I recommend starting with **2. Execution & Brokerage State Desyncs** using `/speckit.specify` and `/speckit.implement`).
