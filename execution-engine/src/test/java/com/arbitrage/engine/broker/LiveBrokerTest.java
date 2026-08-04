package com.arbitrage.engine.broker;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LiveBrokerTest {

    @Test
    void executeRefusesLiveOrders() {
        LiveBroker broker = new LiveBroker();
        Broker.BrokerExecutionRequest request = new Broker.BrokerExecutionRequest(
                UUID.randomUUID(),
                "KO_PEP",
                List.of()
        );
        UnsupportedOperationException error = assertThrows(
                UnsupportedOperationException.class,
                () -> broker.execute(request).block()
        );
        assertTrue(error.getMessage().contains("DRY_RUN=true"));
    }

    @Test
    void cancelAndLiquidateRefuseLiveActions() {
        LiveBroker broker = new LiveBroker();
        assertThrows(UnsupportedOperationException.class, broker::cancelAllOrders);
        assertThrows(UnsupportedOperationException.class, broker::liquidateAllPositions);
    }
}
