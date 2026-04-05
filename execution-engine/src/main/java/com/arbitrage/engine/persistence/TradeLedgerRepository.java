package com.arbitrage.engine.persistence;

import io.r2dbc.spi.Connection;
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.Result;
import io.r2dbc.spi.Statement;
import org.reactivestreams.Publisher;
import reactor.core.publisher.Mono;
import java.math.BigDecimal;
import java.util.UUID;

public class TradeLedgerRepository {

    private final ConnectionFactory connectionFactory;

    public TradeLedgerRepository(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
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
            });
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
