package com.arbitrage.engine.stress;

import com.arbitrage.engine.persistence.RedisOrderSync;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;

public class IdempotencyStressTest {
    private static final Logger logger = LoggerFactory.getLogger(IdempotencyStressTest.class);
    private static RedisOrderSync redisSync;

    @BeforeAll
    static void setup() {
        // Assuming Redis is running on localhost:6379
        redisSync = new RedisOrderSync("redis://localhost:6379");
    }

    @AfterAll
    static void tearDown() {
        redisSync.close();
    }

    @Test
    void testConcurrentIdempotency_Lua() {
        UUID signalId = UUID.randomUUID();
        int concurrency = 100;
        AtomicInteger newCount = new AtomicInteger(0);
        AtomicInteger duplicateCount = new AtomicInteger(0);

        logger.info("Starting stress test with {} concurrent requests for signal {}", concurrency, signalId);

        // Simulate 100 concurrent requests for the same signalId
        Flux.range(1, concurrency)
                .parallel(concurrency)
                .runOn(Schedulers.parallel())
                .flatMap(i -> redisSync.checkAndMarkInFlight(signalId, "PENDING", 60))
                .doOnNext(status -> {
                    if ("NEW".equals(status)) {
                        newCount.incrementAndGet();
                    } else {
                        duplicateCount.incrementAndGet();
                    }
                })
                .sequential()
                .blockLast(Duration.ofSeconds(10));

        logger.info("Stress test completed. NEW={}, DUPLICATE={}", newCount.get(), duplicateCount.get());

        // Assert that exactly ONE request was marked as NEW
        assertEquals(1, newCount.get(), "Exactly one request must be NEW");
        assertEquals(concurrency - 1, duplicateCount.get(), "All other requests must be DUPLICATE");
    }
}
