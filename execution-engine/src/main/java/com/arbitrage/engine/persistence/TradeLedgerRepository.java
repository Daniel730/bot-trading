package com.arbitrage.engine.persistence;

import com.arbitrage.engine.core.ExecutionConstants;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.lettuce.core.api.StatefulRedisConnection;
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.Result;
import io.r2dbc.spi.Statement;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.core.publisher.Mono;
import java.math.BigDecimal;
import java.util.Map;
import java.util.UUID;

public class TradeLedgerRepository {
    private static final Logger logger = LoggerFactory.getLogger(TradeLedgerRepository.class);

    private final ConnectionFactory connectionFactory;
    private final StatefulRedisConnection<String, String> redisConnection;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public TradeLedgerRepository(ConnectionFactory connectionFactory, StatefulRedisConnection<String, String> redisConnection) {
        this.connectionFactory = connectionFactory;
        this.redisConnection = redisConnection;
    }

    public Mono<Void> saveAudit(
        UUID signalId,
        String pairId,
        String ticker,
        String side,
        BigDecimal requestedQty,
        BigDecimal requestedPrice,
        BigDecimal actualVwap,
        String status,
        long latencyMs
    ) {
        return Mono.from(connectionFactory.create())
            .flatMap(connection -> {
                Statement statement = connection.createStatement(
                    "INSERT INTO trade_ledger (signal_id, pair_id, ticker, side, requested_qty, requested_price, actual_vwap, status, latency_ms) " +
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)"
                );
                statement.bind("$1", signalId);
                statement.bind("$2", pairId);
                statement.bind("$3", ticker);
                statement.bind("$4", side);
                statement.bind("$5", requestedQty);
                statement.bind("$6", requestedPrice);
                statement.bind("$7", actualVwap);
                statement.bind("$8", status);
                statement.bind("$9", latencyMs);

                return Mono.from(statement.execute())
                    .flatMap(Result::getRowsUpdated)
                    .then(Mono.from(connection.close()));
            })
            .onErrorResume(e -> {
                logger.error("Failed to persist audit to PostgreSQL for {}. Pushing to DLQ.", signalId, e);
                return pushToDlq(signalId, pairId, ticker, side, requestedQty, requestedPrice, actualVwap, status, latencyMs);
            });
    }

    private Mono<Void> pushToDlq(
        UUID signalId,
        String pairId,
        String ticker,
        String side,
        BigDecimal requestedQty,
        BigDecimal requestedPrice,
        BigDecimal actualVwap,
        String status,
        long latencyMs
    ) {
        Map<String, Object> payload = Map.of(
            "signalId", signalId.toString(),
            "pairId", pairId,
            "ticker", ticker,
            "side", side,
            "requestedQty", requestedQty.toPlainString(),
            "requestedPrice", requestedPrice.toPlainString(),
            "actualVwap", actualVwap.toPlainString(),
            "status", status,
            "latencyMs", latencyMs,
            "timestamp", System.currentTimeMillis()
        );

        try {
            String jsonPayload = objectMapper.writeValueAsString(payload);
            return redisConnection.reactive().lpush(ExecutionConstants.REDIS_DLQ_KEY, jsonPayload).then();
        } catch (JsonProcessingException e) {
            logger.error("CRITICAL: Failed to serialize audit payload for DLQ. Data loss for {}.", signalId, e);
            return Mono.error(e);
        }
    }

    public Mono<String> getStatus(UUID signalId) {
        return Mono.from(connectionFactory.create())
            .flatMapMany(connection -> connection.createStatement(
                "SELECT status FROM trade_ledger WHERE signal_id = $1"
            ).bind("$1", signalId).execute())
            .flatMap(result -> result.map((row, metadata) -> row.get("status", String.class)))
            .next();
    }
}
