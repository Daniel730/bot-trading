package com.arbitrage.engine.persistence;

import com.arbitrage.engine.core.models.ExecutionMode;
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.Result;
import io.r2dbc.spi.Statement;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public class TradeLedgerRepository {

    private final ConnectionFactory connectionFactory;

    public TradeLedgerRepository(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public record TradeAudit(
        String ticker,
        String side,
        BigDecimal requestedQty,
        BigDecimal requestedPrice,
        BigDecimal actualVwap,
        ExecutionMode executionMode,
        String reasoningMetadata
    ) {}

    public Mono<Void> saveAudits(
        UUID signalId,
        String pairId,
        List<TradeAudit> audits,
        String status,
        long latencyMs
    ) {
        return Mono.from(connectionFactory.create())
            .flatMap(connection -> 
                Mono.from(connection.beginTransaction())
                    .then(Mono.defer(() -> {
                        Statement statement = connection.createStatement(
                            "INSERT INTO trade_ledger (signal_id, pair_id, ticker, side, requested_qty, requested_price, actual_vwap, status, latency_ms, execution_mode, reasoning_metadata) " +
                            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)"
                        );

                        for (int i = 0; i < audits.size(); i++) {
                            TradeAudit audit = audits.get(i);
                            statement.bind(0, signalId);
                            statement.bind(1, pairId);
                            statement.bind(2, audit.ticker());
                            statement.bind(3, audit.side());
                            statement.bind(4, audit.requestedQty());
                            statement.bind(5, audit.requestedPrice());
                            statement.bind(6, audit.actualVwap());
                            statement.bind(7, status);
                            statement.bind(8, latencyMs);
                            statement.bind(9, audit.executionMode().name());
                            statement.bind(10, audit.reasoningMetadata());
                            if (i < audits.size() - 1) {
                                statement.add();
                            }
                        }

                        return Flux.from(statement.execute())
                            .flatMap(Result::getRowsUpdated)
                            .then();
                    }))
                    .then(Mono.from(connection.commitTransaction()))
                    .onErrorResume(e -> Mono.from(connection.rollbackTransaction()).then(Mono.error(e)))
                    .then(Mono.from(connection.close()))
            );
    }

    public Mono<String> getStatus(UUID signalId) {
        return Mono.from(connectionFactory.create())
            .flatMapMany(connection -> connection.createStatement(
                "SELECT status FROM trade_ledger WHERE signal_id = $1"
            ).bind(0, signalId).execute())
            .flatMap(result -> result.map((row, metadata) -> row.get("status", String.class)))
            .next();
    }
}
