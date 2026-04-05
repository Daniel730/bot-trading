package com.arbitrage.engine.persistence;

import io.r2dbc.spi.Connection;
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.Result;
import io.r2dbc.spi.Statement;
import org.reactivestreams.Publisher;
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
        BigDecimal actualVwap
    ) {}

    public Mono<Void> saveAudits(
        UUID signalId,
        String pairId,
        List<TradeAudit> audits,
        String status,
        long latencyMs
    ) {
        return Mono.from(connectionFactory.create())
            .flatMap(connection -> {
                Statement statement = connection.createStatement(
                    "INSERT INTO trade_ledger (signal_id, pair_id, ticker, side, requested_qty, requested_price, actual_vwap, status, latency_ms) " +
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)"
                );

                for (int i = 0; i < audits.size(); i++) {
                    TradeAudit audit = audits.get(i);
                    statement.bind("$1", signalId);
                    statement.bind("$2", pairId);
                    statement.bind("$3", audit.ticker());
                    statement.bind("$4", audit.side());
                    statement.bind("$5", audit.requestedQty());
                    statement.bind("$6", audit.requestedPrice());
                    statement.bind("$7", audit.actualVwap());
                    statement.bind("$8", status);
                    statement.bind("$9", latencyMs);
                    if (i < audits.size() - 1) {
                        statement.add();
                    }
                }

                return Mono.from(statement.execute())
                    .flatMap(Result::getRowsUpdated)
                    .then(Mono.from(connection.close()));
            });
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
        return saveAudits(signalId, pairId, List.of(new TradeAudit(ticker, side, requestedQty, requestedPrice, actualVwap)), status, latencyMs);
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
