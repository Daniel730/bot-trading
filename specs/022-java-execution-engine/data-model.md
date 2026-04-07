# Data Model: High-Performance Execution Engine (The Muscle)

## PostgreSQL (Persistent Audits)

### Table: `trade_ledger`
Records every execution request, its calculated metrics, and the final outcome from the broker.

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID (PK) | Internal unique ID for the ledger entry. |
| `signal_id` | UUID | Links to the Python `agent_reasoning` signal. |
| `pair_id` | VARCHAR(20) | e.g., "KO_PEP". |
| `ticker` | VARCHAR(10) | The specific ticker being traded. |
| `side` | VARCHAR(4) | BUY or SELL. |
| `requested_qty` | DECIMAL(18,10) | Quantity requested by the brain. |
| `requested_price` | DECIMAL(18,10) | Target price requested by the brain. |
| `actual_vwap` | DECIMAL(18,10) | VWAP calculated by walking the L2 book. |
| `slippage_pct` | DECIMAL(10,6) | `(Actual_VWAP - Target) / Target`. |
| `status` | VARCHAR(20) | SUCCESS, REJECTED_SLIPPAGE, REJECTED_DEPTH, BROKER_ERROR. |
| `broker_order_id` | VARCHAR(50) | ID returned by the exchange (if successful). |
| `latency_ms` | INTEGER | Time from gRPC receipt to order submission. |
| `created_at` | TIMESTAMP | Request arrival time. |

---

## Redis (Transient State)

### Key Pattern: `execution:inflight:{signal_id}` (Hash)
Used for deduplication and recovery of active orders.

| Field | Description |
| :--- | :--- |
| `status` | PENDING, SENT, REJECTED. |
| `broker_id` | The broker's order ID. |
| `legs_count` | Number of legs in the atomic trade. |
| `timestamp` | Time the hash was created. |

### Key Pattern: `ratelimit:broker:{api_key}` (String/Counter)
Atomic counter for broker API rate limiting.
