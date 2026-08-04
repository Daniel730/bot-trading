package com.arbitrage.engine.broker;

import reactor.core.publisher.Mono;

/**
 * Intentionally disabled stub. The Java engine must run with {@code DRY_RUN=true}
 * and route through {@link MockBroker}; live brokerage remains on the Python path.
 */
public class LiveBroker implements Broker {
    private static final String DISABLED =
            "LiveBroker is intentionally disabled. Set DRY_RUN=true; "
                    + "Java live brokerage is not implemented.";

    @Override
    public Mono<BrokerExecutionResponse> execute(BrokerExecutionRequest request) {
        return Mono.error(new UnsupportedOperationException(DISABLED));
    }

    @Override
    public int cancelAllOrders() {
        throw new UnsupportedOperationException(DISABLED);
    }

    @Override
    public int liquidateAllPositions() {
        throw new UnsupportedOperationException(DISABLED);
    }
}
