# Data Model: Production-Grade Polish & Reliability Enforcement

## Existing Tables (Updated Usage)

### `kalman_state`

Used to persist the state of each pair's Kalman Filter to survive restarts.

- `pair_id`: Unique identifier for the pair (FK to `arbitrage_pairs`).
- `timestamp`: Time of last update.
- `alpha`: Intercept value.
- `beta`: Hedge ratio value.
- `p_matrix`: State covariance matrix (JSON string).
- `q_matrix`: Process noise covariance matrix (JSON string).
- `r_value`: Measurement noise variance.
- `ve`: Innovation variance (Z-score denominator).

### `system_state`

Used for generic system-level state tracking.

- `key`: State key (e.g., `operational_status`, `consecutive_api_timeouts`).
- `value`: State value.

## Internal State (In-Memory)

### `BrokerageService` Cache

Used to prevent API rate-limiting.

- `_cache`: Dictionary mapping endpoint (e.g., `/portfolio`) to a tuple of `(data, timestamp)`.
- `TTL`: Fixed at 5 seconds.
