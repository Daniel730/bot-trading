package com.arbitrage.engine.integration;

import com.arbitrage.engine.api.L2FeedService;
import com.arbitrage.engine.broker.Broker;
import com.arbitrage.engine.broker.MockBroker;
import com.arbitrage.engine.core.models.ExecutionLeg;
import com.arbitrage.engine.core.models.L2OrderBook;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

class ShadowModeBenchmarkTest {

    @Test
    void benchmarkShadowModeLatency() {
        L2FeedService l2FeedService = Mockito.mock(L2FeedService.class);
        MockBroker mockBroker = new MockBroker(l2FeedService);
        
        L2OrderBook book = new L2OrderBook("KO", System.currentTimeMillis(),
                List.of(new L2OrderBook.Level(new BigDecimal("50.00"), new BigDecimal("1000"))),
                List.of());
        when(l2FeedService.getLatestBook(Mockito.anyString())).thenReturn(book);

        Broker.BrokerExecutionRequest request = new Broker.BrokerExecutionRequest(
                UUID.randomUUID(),
                "KO_PEP",
                List.of(
                    new Broker.BrokerLeg("KO", ExecutionLeg.Side.BUY, new BigDecimal("10"), new BigDecimal("50.00")),
                    new Broker.BrokerLeg("PEP", ExecutionLeg.Side.SELL, new BigDecimal("5"), new BigDecimal("100.00"))
                )
        );

        long start = System.currentTimeMillis();
        for (int i = 0; i < 100; i++) {
            mockBroker.execute(request).block();
        }
        long end = System.currentTimeMillis();
        
        long avgLatency = (end - start) / 100;
        System.out.println("Average Shadow Mode Latency: " + avgLatency + "ms");
        
        assertTrue(avgLatency < 100, "Average latency should be less than 100ms");
    }
}
