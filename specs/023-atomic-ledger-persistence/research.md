# Research: Atomic Ledger Persistence & Idempotency

## Decision: Redis Lua Script for Atomic Idempotency
**Decision**: Use a Lua script to implement `GETSET`-like behavior with a TTL to ensure atomicity of the "check-and-reserve" operation.

**Rationale**: 
- A simple `SETNX` (or `hsetnx`) only tells us if the key was set, but we also need to handle the case where a request is already being processed.
- A Lua script allows us to check if the key exists, read its current status, and if it doesn't exist, set it to "IN_PROGRESS" all in one atomic step.
- This prevents the race condition between `redisSync.exists(signalId).block()` and `redisSync.markInFlight(...)`.

**Lua Script**:
```lua
local key = KEYS[1]
local status = ARGV[1]
local timestamp = ARGV[2]
local ttl = ARGV[3]

if redis.call("EXISTS", key) == 1 then
    return redis.call("HGET", key, "status")
else
    redis.call("HSET", key, "status", status, "timestamp", timestamp)
    redis.call("EXPIRE", key, ttl)
    return "OK"
end
```

## Decision: Blocking Ledger Persistence via Transactional Hooks
**Decision**: Replace `.subscribe()` with a blocking wait or a guaranteed completion before gRPC `onNext`.

**Rationale**:
- The current implementation uses `.subscribe()`, which is "fire and forget". If the DB is down, the gRPC caller gets a success message while the audit is lost.
- We must use `.block()` (or better, switch the entire `executeTrade` to be truly reactive, but for now, ensuring completion is key).
- Since we are using R2DBC, we should chain the persistence Mono to the response Mono.

## Decision: Dead-Letter Queue for Persistence Failures
**Decision**: Implement a specific, strictly-typed Redis list named `dlq:execution:audit_ledger` if PostgreSQL/R2DBC fails.

**Rationale**:
- If the primary ledger fails, we cannot simply fail the trade if the broker already executed it.
- We will catch persistence errors and push the payload to `dlq:execution:audit_ledger`.
- A specific queue ensures absolute certainty of the payload schema for future replay/reconciliation, avoiding deserialization issues with mixed data.

## Alternatives Considered
- **Distributed Locks (Redlock)**: Overkill for single-signal idempotency.
- **Transactional Outbox Pattern**: Too complex for the current MVP scope; Redis DLQ is simpler for now.
