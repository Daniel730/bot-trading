package com.arbitrage.engine.broker;

import com.arbitrage.engine.api.L2FeedService;
import com.arbitrage.engine.core.models.ExecutionLeg;
import com.arbitrage.engine.core.models.L2OrderBook;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.when;

class MockBrokerTest {
    private L2FeedService l2FeedService;
    private MockBroker mockBroker;

    @BeforeEach
    void setUp() {
        l2FeedService = Mockito.mock(L2FeedService.class);
        mockBroker = new MockBroker(l2FeedService);
    }

    @Test
    void execute_Success() {
        UUID signalId = UUID.randomUUID();
        L2OrderBook book = new L2OrderBook("KO", System.currentTimeMillis(),
                List.of(new L2OrderBook.Level(new BigDecimal("50.00"), new BigDecimal("100"))),
                List.of());
        
        when(l2FeedService.getLatestBook("KO")).thenReturn(book);

        Broker.BrokerExecutionRequest request = new Broker.BrokerExecutionRequest(
                signalId,
                "KO_PEP",
                List.of(new Broker.BrokerLeg("KO", ExecutionLeg.Side.BUY, new BigDecimal("10"), new BigDecimal("50.00")))
        );

        Broker.BrokerExecutionResponse response = mockBroker.execute(request).block();

        assertTrue(response.success());
        assertEquals(1, response.finalFillPrices().size());
        assertEquals(0, new BigDecimal("50.00").compareTo(response.finalFillPrices().get(0)));
    }

    @Test
    void execute_StaleData_Failure() {
        UUID signalId = UUID.randomUUID();
        // 1 second old
        L2OrderBook book = new L2OrderBook("KO", System.currentTimeMillis() - 1000,
                List.of(new L2OrderBook.Level(new BigDecimal("50.00"), new BigDecimal("100"))),
                List.of());
        
        when(l2FeedService.getLatestBook("KO")).thenReturn(book);

        Broker.BrokerExecutionRequest request = new Broker.BrokerExecutionRequest(
                signalId,
                "KO_PEP",
                List.of(new Broker.BrokerLeg("KO", ExecutionLeg.Side.BUY, new BigDecimal("10"), new BigDecimal("50.00")))
        );

        Broker.BrokerExecutionResponse response = mockBroker.execute(request).block();

        assertFalse(response.success());
        assertTrue(response.message().contains("Stale market data"));
    }

    @Test
    void execute_InsufficientDepth_Failure() {
        UUID signalId = UUID.randomUUID();
        L2OrderBook book = new L2OrderBook("KO", System.currentTimeMillis(),
                List.of(new L2OrderBook.Level(new BigDecimal("50.00"), new BigDecimal("5"))),
                List.of());
        
        when(l2FeedService.getLatestBook("KO")).thenReturn(book);

        Broker.BrokerExecutionRequest request = new Broker.BrokerExecutionRequest(
                signalId,
                "KO_PEP",
                List.of(new Broker.BrokerLeg("KO", ExecutionLeg.Side.BUY, new BigDecimal("10"), new BigDecimal("50.00")))
        );

        Broker.BrokerExecutionResponse response = mockBroker.execute(request).block();

        assertFalse(response.success());
        assertTrue(response.message().contains("market depth"));
    }
}
