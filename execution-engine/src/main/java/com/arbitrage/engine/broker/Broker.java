package com.arbitrage.engine.broker;

import com.arbitrage.engine.core.models.ExecutionLeg;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public interface Broker {
    public record BrokerExecutionRequest(
            UUID signalId,
            String pairId,
            List<BrokerLeg> legs
    ) {}

    public record BrokerLeg(
            String ticker,
            ExecutionLeg.Side side,
            BigDecimal quantity,
            BigDecimal vwap
    ) {}

    public record BrokerExecutionResponse(
            boolean success,
            String message,
            List<BigDecimal> finalFillPrices
    ) {}

    Mono<BrokerExecutionResponse> execute(BrokerExecutionRequest request);
}
