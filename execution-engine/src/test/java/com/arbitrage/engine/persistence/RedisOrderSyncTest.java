package com.arbitrage.engine.persistence;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
class RedisOrderSyncTest {

    @Container
    static GenericContainer<?> redis = new GenericContainer<>(DockerImageName.parse("redis:7-alpine"))
            .withExposedPorts(6379);

    private static RedisOrderSync redisSync;

    @BeforeAll
    static void setup() {
        String redisUri = String.format("redis://%s:%d", redis.getHost(), redis.getFirstMappedPort());
        redisSync = new RedisOrderSync(redisUri);
    }

    @AfterAll
    static void tearDown() {
        redisSync.close();
    }

    @Test
    void testCheckAndSetIdempotency_NewOrder() {
        UUID signalId = UUID.randomUUID();
        String result = redisSync.checkAndSetIdempotency(signalId).block();
        assertEquals("OK", result);

        String status = redisSync.getStatus(signalId).block();
        assertEquals("PENDING", status);
    }

    @Test
    void testCheckAndSetIdempotency_DuplicateOrder() {
        UUID signalId = UUID.randomUUID();
        
        // First call
        String result1 = redisSync.checkAndSetIdempotency(signalId).block();
        assertEquals("OK", result1);

        // Second call
        String result2 = redisSync.checkAndSetIdempotency(signalId).block();
        assertEquals("PENDING", result2);
    }

    @Test
    void testUpdateStatus() {
        UUID signalId = UUID.randomUUID();
        redisSync.checkAndSetIdempotency(signalId).block();
        
        redisSync.updateStatus(signalId, "SUCCESS").block();
        
        String status = redisSync.getStatus(signalId).block();
        assertEquals("SUCCESS", status);

        // Check that idempotency now returns SUCCESS
        String result = redisSync.checkAndSetIdempotency(signalId).block();
        assertEquals("SUCCESS", result);
    }
}
