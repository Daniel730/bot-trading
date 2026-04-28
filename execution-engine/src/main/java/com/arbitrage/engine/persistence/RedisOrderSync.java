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
        )).then(commands.expire(key, 3600L)).then();
    }

    public Mono<Boolean> exists(UUID signalId) {
        return connection.reactive().exists("execution:inflight:" + signalId.toString())
                .map(count -> count > 0);
    }

    public Mono<String> getStatus(UUID signalId) {
        return connection.reactive().hget("execution:inflight:" + signalId.toString(), "status");
    }

    /**
     * Atomically check if a signal ID exists and mark it as in-flight if it does not.
     * Uses a Lua script for atomicity to prevent race conditions under load.
     * 
     * @param signalId The UUID of the signal.
     * @param initialStatus The status to set if new.
     * @param ttlSeconds Time-to-live for the idempotency lock.
     * @return Mono<String> returns "NEW" if it was not present, or the existing "status" if it was.
     */
    public Mono<String> checkAndMarkInFlight(UUID signalId, String initialStatus, int ttlSeconds) {
        String key = "execution:inflight:" + signalId.toString();
        String script = 
            "if redis.call('EXISTS', KEYS[1]) == 1 then " +
            "  return redis.call('HGET', KEYS[1], 'status') " +
            "else " +
            "  redis.call('HSET', KEYS[1], 'status', ARGV[1], 'timestamp', ARGV[2]) " +
            "  redis.call('EXPIRE', KEYS[1], ARGV[3]) " +
            "  return 'NEW' " +
            "end";

        return connection.reactive().eval(
            script, 
            io.lettuce.core.ScriptOutputType.VALUE, 
            new String[]{key}, 
            initialStatus, 
            String.valueOf(System.currentTimeMillis()), 
            String.valueOf(ttlSeconds)
        ).next().map(res -> res == null ? "NEW" : res.toString());
    }

    public void close() {
        connection.close();
        redisClient.shutdown();
    }
}
