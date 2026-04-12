package com.arbitrage.engine.integration;

import com.arbitrage.engine.api.ExecutionServiceImpl;
import com.arbitrage.engine.api.L2FeedService;
import com.arbitrage.engine.core.models.L2OrderBook;
import com.arbitrage.engine.grpc.*;
import com.arbitrage.engine.persistence.RedisOrderSync;
import com.arbitrage.engine.persistence.TradeLedgerRepository;
import io.grpc.stub.StreamObserver;
import io.r2dbc.postgresql.PostgresqlConnectionConfiguration;
import io.r2dbc.postgresql.PostgresqlConnectionFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

@Testcontainers
class ExecutionIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:15-alpine")
            .withInitScript("init.sql"); // I'll create this

    private static TradeLedgerRepository repository;
    private static RedisOrderSync redisSync;
    private static L2FeedService l2FeedService;
    private static ExecutionServiceImpl service;

    @BeforeAll
    static void setup() {
        PostgresqlConnectionFactory connectionFactory = new PostgresqlConnectionFactory(
                PostgresqlConnectionConfiguration.builder()
                        .host(postgres.getHost())
                        .port(postgres.getFirstMappedPort())
                        .username(postgres.getUsername())
                        .password(postgres.getPassword())
                        .database(postgres.getDatabaseName())
                        .build()
        );
        repository = new TradeLedgerRepository(connectionFactory);
        
        // Mock Redis for now to avoid needing a Redis container
        redisSync = mock(RedisOrderSync.class);
        when(redisSync.markInFlight(Mockito.any(), anyString())).thenReturn(reactor.core.publisher.Mono.empty());
        
        l2FeedService = mock(L2FeedService.class);
        
        service = new ExecutionServiceImpl(repository, redisSync, l2FeedService);
    }

    @Test
    void testExecuteTrade_Success() throws InterruptedException {
        String signalId = UUID.randomUUID().toString();
        
        when(l2FeedService.getLatestBook("KO")).thenReturn(new L2OrderBook("KO", System.currentTimeMillis(),
            List.of(new L2OrderBook.Level(new BigDecimal("50.00"), new BigDecimal("100"))), 
            List.of()));

        ExecutionRequest request = ExecutionRequest.newBuilder()
                .setSignalId(signalId)
                .setPairId("KO_PEP")
                .setTimestampNs(System.nanoTime())
                .setMaxSlippagePct(0.01)
                .addLegs(ExecutionRequest.ExecutionLeg.newBuilder()
                        .setTicker("KO")
                        .setSide(Side.SIDE_BUY)
                        .setQuantity(10.0)
                        .setTargetPrice(50.0)
                        .build())
                .build();

        CountDownLatch latch = new CountDownLatch(1);
        final ExecutionResponse[] responseHolder = new ExecutionResponse[1];

        service.executeTrade(request, new StreamObserver<ExecutionResponse>() {
            @Override
            public void onNext(ExecutionResponse value) {
                responseHolder[0] = value;
            }

            @Override
            public void onError(Throwable t) {
                fail(t.getMessage());
            }

            @Override
            public void onCompleted() {
                latch.countDown();
            }
        });

        assertTrue(latch.await(5, TimeUnit.SECONDS));
        assertNotNull(responseHolder[0]);
        assertEquals(ExecutionStatus.STATUS_SUCCESS, responseHolder[0].getStatus());
        assertEquals(50.0, responseHolder[0].getActualVwap());
    }

    @Test
    void testExecuteTrade_SlippageVeto() throws InterruptedException {
        String signalId = UUID.randomUUID().toString();
        
        // Price moved to 51.00, which is > 50.00 * 1.01
        when(l2FeedService.getLatestBook("KO")).thenReturn(new L2OrderBook("KO", System.currentTimeMillis(),
            List.of(new L2OrderBook.Level(new BigDecimal("51.00"), new BigDecimal("100"))), 
            List.of()));

        ExecutionRequest request = ExecutionRequest.newBuilder()
                .setSignalId(signalId)
                .setPairId("KO_PEP")
                .setTimestampNs(System.nanoTime())
                .setMaxSlippagePct(0.01)
                .addLegs(ExecutionRequest.ExecutionLeg.newBuilder()
                        .setTicker("KO")
                        .setSide(Side.SIDE_BUY)
                        .setQuantity(10.0)
                        .setTargetPrice(50.0)
                        .build())
                .build();

        CountDownLatch latch = new CountDownLatch(1);
        final ExecutionResponse[] responseHolder = new ExecutionResponse[1];

        service.executeTrade(request, new StreamObserver<ExecutionResponse>() {
            @Override
            public void onNext(ExecutionResponse value) {
                responseHolder[0] = value;
            }

            @Override
            public void onError(Throwable t) {
                fail(t.getMessage());
            }

            @Override
            public void onCompleted() {
                latch.countDown();
            }
        });

        assertTrue(latch.await(5, TimeUnit.SECONDS));
        assertNotNull(responseHolder[0]);
        assertEquals(ExecutionStatus.STATUS_REJECTED_SLIPPAGE, responseHolder[0].getStatus());
    }

    @Test
    void testExecuteTrade_LatencyRejection() throws InterruptedException {
        String signalId = UUID.randomUUID().toString();
        
        // Request timestamp is 1 second in the past
        ExecutionRequest request = ExecutionRequest.newBuilder()
                .setSignalId(signalId)
                .setPairId("KO_PEP")
                .setTimestampNs(System.nanoTime() - 1_000_000_000L) 
                .setMaxSlippagePct(0.01)
                .addLegs(ExecutionRequest.ExecutionLeg.newBuilder()
                        .setTicker("KO")
                        .setSide(Side.SIDE_BUY)
                        .setQuantity(10.0)
                        .setTargetPrice(50.0)
                        .build())
                .build();

        CountDownLatch latch = new CountDownLatch(1);
        final ExecutionResponse[] responseHolder = new ExecutionResponse[1];

        service.executeTrade(request, new StreamObserver<ExecutionResponse>() {
            @Override
            public void onNext(ExecutionResponse value) {
                responseHolder[0] = value;
            }

            @Override
            public void onError(Throwable t) {
                fail(t.getMessage());
            }

            @Override
            public void onCompleted() {
                latch.countDown();
            }
        });

        assertTrue(latch.await(5, TimeUnit.SECONDS));
        assertNotNull(responseHolder[0]);
        assertEquals(ExecutionStatus.STATUS_REJECTED_LATENCY, responseHolder[0].getStatus());
        assertTrue(responseHolder[0].getMessage().contains("Stale Alpha"));
    }

    @Test
    void testExecuteTrade_MultiLeg_AtomicFailure() throws InterruptedException {
        String signalId = UUID.randomUUID().toString();
        
        // KO is fine
        when(l2FeedService.getLatestBook("KO")).thenReturn(new L2OrderBook("KO", System.currentTimeMillis(),
            List.of(new L2OrderBook.Level(new BigDecimal("50.00"), new BigDecimal("100"))), 
            List.of()));
            
        // PEP has slippage (Price 101.00 > Target 100.00 * 1.005)
        when(l2FeedService.getLatestBook("PEP")).thenReturn(new L2OrderBook("PEP", System.currentTimeMillis(),
            List.of(new L2OrderBook.Level(new BigDecimal("101.00"), new BigDecimal("100"))), 
            List.of()));

        ExecutionRequest request = ExecutionRequest.newBuilder()
                .setSignalId(signalId)
                .setPairId("KO_PEP")
                .setTimestampNs(System.nanoTime())
                .setMaxSlippagePct(0.005)
                .addLegs(ExecutionRequest.ExecutionLeg.newBuilder()
                        .setTicker("KO")
                        .setSide(Side.SIDE_BUY)
                        .setQuantity(10.0)
                        .setTargetPrice(50.0)
                        .build())
                .addLegs(ExecutionRequest.ExecutionLeg.newBuilder()
                        .setTicker("PEP")
                        .setSide(Side.SIDE_BUY)
                        .setQuantity(5.0)
                        .setTargetPrice(100.0)
                        .build())
                .build();

        CountDownLatch latch = new CountDownLatch(1);
        final ExecutionResponse[] responseHolder = new ExecutionResponse[1];

        service.executeTrade(request, new StreamObserver<ExecutionResponse>() {
            @Override
            public void onNext(ExecutionResponse value) {
                responseHolder[0] = value;
            }

            @Override
            public void onError(Throwable t) {
                fail(t.getMessage());
            }

            @Override
            public void onCompleted() {
                latch.countDown();
            }
        });

        assertTrue(latch.await(5, TimeUnit.SECONDS));
        assertNotNull(responseHolder[0]);
        // The entire request should be rejected because PEP failed
        assertEquals(ExecutionStatus.STATUS_REJECTED_SLIPPAGE, responseHolder[0].getStatus());
    }
}
