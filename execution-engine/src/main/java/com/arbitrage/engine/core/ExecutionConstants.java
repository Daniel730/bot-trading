package com.arbitrage.engine.core;

public class ExecutionConstants {
    public static final String REDIS_INFLIGHT_PREFIX = "execution:inflight:";
    public static final String REDIS_DLQ_KEY = "dlq:execution:audit_ledger";
    
    // Idempotency lock TTL (5 minutes as catastrophic fallback)
    public static final long IDEMPOTENCY_TTL_SECONDS = 300;
}
