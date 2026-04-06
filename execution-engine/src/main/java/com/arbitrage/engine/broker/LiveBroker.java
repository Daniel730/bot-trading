package com.arbitrage.engine.broker;

import reactor.core.publisher.Mono;

public class LiveBroker implements Broker {
    @Override
    public Mono<BrokerExecutionResponse> execute(BrokerExecutionRequest request) {
        // Placeholder for real brokerage integration
        return Mono.just(new BrokerExecutionResponse(false, "LiveBroker integration not yet implemented", null));
    }
}
