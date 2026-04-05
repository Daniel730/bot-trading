package com.arbitrage.engine.persistence;

import com.arbitrage.engine.core.ExecutionConstants;
import io.lettuce.core.RedisClient;
import io.lettuce.core.ScriptOutputType;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.reactive.RedisReactiveCommands;
import reactor.core.publisher.Mono;
import java.util.Map;
import java.util.UUID;

public class RedisOrderSync {

    private final RedisClient redisClient;
    private final StatefulRedisConnection<String, String> connection;
    private String scriptSha;

    private static final String LUA_IDEMPOTENCY_SCRIPT = 
        "local key = KEYS[1]\n" +
        "local status = ARGV[1]\n" +
        "local timestamp = ARGV[2]\n" +
        "local ttl = ARGV[3]\n" +
        "\n" +
        "if redis.call('EXISTS', key) == 1 then\n" +
        "    return redis.call('HGET', key, 'status')\n" +
        "else\n" +
        "    redis.call('HSET', key, 'status', status, 'timestamp', timestamp)\n" +
        "    redis.call('EXPIRE', key, ttl)\n" +
        "    return 'OK'\n" +
        "end";

    public RedisOrderSync(String redisUri) {
        this.redisClient = RedisClient.create(redisUri);
        this.connection = redisClient.connect();
        // Pre-load script for efficiency and to avoid virtual thread pinning issues with raw script execution
        this.scriptSha = connection.sync().scriptLoad(LUA_IDEMPOTENCY_SCRIPT);
    }

    /**
     * Atomically check if an order is already being processed and set it to PENDING if not.
     * @return Mono with "OK" if set, or current status if already exists.
     */
    public Mono<String> checkAndSetIdempotency(UUID signalId) {
        String key = ExecutionConstants.REDIS_INFLIGHT_PREFIX + signalId.toString();
        String timestamp = String.valueOf(System.currentTimeMillis());
        String ttl = String.valueOf(ExecutionConstants.IDEMPOTENCY_TTL_SECONDS);
        
        return connection.reactive().evalsha(
            scriptSha, 
            ScriptOutputType.STATUS, 
            new String[]{key}, 
            "PENDING", timestamp, ttl
        );
    }

    public Mono<Void> updateStatus(UUID signalId, String status) {
        String key = ExecutionConstants.REDIS_INFLIGHT_PREFIX + signalId.toString();
        return connection.reactive().hset(key, "status", status).then();
    }

    @Deprecated
    public Mono<Void> markInFlight(UUID signalId, String status) {
        RedisReactiveCommands<String, String> commands = connection.reactive();
        String key = ExecutionConstants.REDIS_INFLIGHT_PREFIX + signalId.toString();
        
        return commands.hset(key, Map.of(
            "status", status,
            "timestamp", String.valueOf(System.currentTimeMillis())
        )).then();
    }

    public Mono<Boolean> exists(UUID signalId) {
        return connection.reactive().exists(ExecutionConstants.REDIS_INFLIGHT_PREFIX + signalId.toString())
                .map(count -> count > 0);
    }

    public Mono<String> getStatus(UUID signalId) {
        return connection.reactive().hget(ExecutionConstants.REDIS_INFLIGHT_PREFIX + signalId.toString(), "status");
    }

    public void close() {
        connection.close();
        redisClient.shutdown();
    }
}
