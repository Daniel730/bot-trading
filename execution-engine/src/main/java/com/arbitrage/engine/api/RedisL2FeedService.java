package com.arbitrage.engine.api;

import com.arbitrage.engine.core.models.L2OrderBook;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RedisL2FeedService implements L2FeedService, AutoCloseable {
    private static final Logger logger = LoggerFactory.getLogger(RedisL2FeedService.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final RedisClient client;
    private final StatefulRedisConnection<String, String> connection;
    private final RedisCommands<String, String> commands;

    public RedisL2FeedService(String redisUri) {
        this.client = RedisClient.create(redisUri);
        this.connection = client.connect();
        this.commands = connection.sync();
    }

    @Override
    public L2OrderBook getLatestBook(String ticker) {
        for (String key : new String[]{"l2:" + ticker, "l2_book:" + ticker, "orderbook:" + ticker}) {
            String payload = commands.get(key);
            if (payload == null || payload.isBlank()) {
                continue;
            }
            try {
                return MAPPER.readValue(payload, L2OrderBook.class);
            } catch (Exception exc) {
                logger.warn("Invalid L2 payload at Redis key {}: {}", key, exc.getMessage());
            }
        }
        return null;
    }

    @Override
    public void close() {
        connection.close();
        client.shutdown();
    }
}
