package com.arbitrage.engine.persistence;

import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.reactive.RedisReactiveCommands;
import reactor.core.publisher.Mono;
import java.util.Map;
import java.util.UUID;

public class RedisOrderSync {

    private final RedisClient redisClient;
    private final StatefulRedisConnection<String, String> connection;

    public RedisOrderSync(String redisUri) {
        this.redisClient = RedisClient.create(redisUri);
        this.connection = redisClient.connect();
    }

    public Mono<Void> markInFlight(UUID signalId, String status) {
        RedisReactiveCommands<String, String> commands = connection.reactive();
        String key = "execution:inflight:" + signalId.toString();
        
        return commands.hset(key, Map.of(
            "status", status,
            "timestamp", String.valueOf(System.currentTimeMillis())
        )).then();
    }

    public Mono<Boolean> exists(UUID signalId) {
        return connection.reactive().exists("execution:inflight:" + signalId.toString())
                .map(count -> count > 0);
    }

    public Mono<String> getStatus(UUID signalId) {
        return connection.reactive().hget("execution:inflight:" + signalId.toString(), "status");
    }

    public void close() {
        connection.close();
        redisClient.shutdown();
    }
}
