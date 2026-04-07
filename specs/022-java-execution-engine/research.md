# Research: High-Performance Execution Engine (The Muscle)

## Decision: Java 21 Virtual Threads (Project Loom)
**Decision**: Use Java 21 Virtual Threads for gRPC request handling.
**Rationale**: Traditional thread-per-request models in Java are resource-heavy and risk thread exhaustion under high load. Virtual threads are lightweight and allow the application to handle thousands of concurrent I/O-bound requests (PostgreSQL, Redis) without the complexity of callback-based asynchronous programming. This provides the best balance of maintainability and performance for the 2ms P99 goal.
**Alternatives Considered**:
*   **LMAX Disruptor**: Rejected as the primary concurrency model due to its high complexity. It will be reserved only for the internal "execution queue" if Virtual Threads show unexpected jitter.
*   **Standard Reactive (Project Reactor)**: Rejected. Virtual threads provide similar throughput with much simpler, blocking-style code structure.

## Decision: R2DBC for PostgreSQL
**Decision**: Use `r2dbc-postgresql` with `r2dbc-pool`.
**Rationale**: R2DBC allows the application to write audits to PostgreSQL without blocking the Virtual Thread's execution flow. To achieve sub-2ms latency, the audit write is fired as a background task. 
**Alternatives Considered**:
*   **JDBC with Thread Pool**: Rejected. JDBC is inherently blocking, which would waste Virtual Threads and risk latency spikes during connection wait.

## Decision: BigDecimal for VWAP Calculation
**Decision**: Use `java.math.BigDecimal` for all core math.
**Rationale**: Senior Developer mandate requires zero precision loss. `BigDecimal` provides the necessary 10-decimal precision.
**Performance Note**: While `BigDecimal` is slower than `double`, at our scale (15-50 shares), the calculation takes nanoseconds, which is negligible compared to network RTT and gRPC overhead.
**Alternatives Considered**:
*   **Long Scaled Integer**: Considered for microsecond performance (e.g., price * 1,000,000), but `BigDecimal` is more readable and less error-prone for our initial implementation.

## Decision: Lettuce for Redis Synchronization
**Decision**: Use Lettuce with Reactive API for "In-Flight" order tracking.
**Rationale**: Lettuce is non-blocking and natively supports Redis Sentinel/Cluster. It allows us to update the "sent" state of an order in Redis concurrently with the exchange submission.
**Alternatives Considered**:
*   **Jedis**: Rejected. Jedis is primarily synchronous and thread-unsafe in many configurations, making it unsuitable for a high-concurrency Java 21 environment.

## "Walk the Book" Edge Cases
**Finding**:
1.  **Empty Book**: If the L2 book is empty, return `REJECTED_NO_LIQUIDITY`.
2.  **Partial Book Fill**: If the requested quantity (e.g., 100 shares) exceeds the total depth of the L2 book (e.g., 80 shares), the trade MUST be rejected with `INSUFFICIENT_MARKET_DEPTH` to prevent executing a partial order that breaks the arbitrage symmetry.
3.  **Crossed Book**: If the L2 book is "crossed" (Best Ask < Best Bid), the data is considered corrupt; log a critical warning and reject.
