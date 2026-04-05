package com.arbitrage.engine.api;

import com.arbitrage.engine.core.VwapCalculator;
import com.arbitrage.engine.core.models.ExecutionLeg;
import com.arbitrage.engine.core.models.L2OrderBook;
import com.arbitrage.engine.grpc.*;
import com.arbitrage.engine.persistence.RedisOrderSync;
import com.arbitrage.engine.persistence.TradeLedgerRepository;
import com.arbitrage.engine.risk.SlippageGuard;
import io.grpc.stub.StreamObserver;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.util.UUID;

public class ExecutionServiceImpl extends ExecutionServiceGrpc.ExecutionServiceImplBase {
    private static final Logger logger = LoggerFactory.getLogger(ExecutionServiceImpl.class);

    private final VwapCalculator vwapCalculator = new VwapCalculator();
    private final SlippageGuard slippageGuard = new SlippageGuard();
    private final TradeLedgerRepository repository;
    private final RedisOrderSync redisSync;
    private final L2FeedService l2FeedService;
    private final Timer executionTimer = Timer.builder("execution.latency")
            .description("Time taken for execution loop")
            .publishPercentiles(0.5, 0.9, 0.95, 0.99)
            .register(Metrics.globalRegistry);

    public ExecutionServiceImpl(TradeLedgerRepository repository, RedisOrderSync redisSync, L2FeedService l2FeedService) {
        this.repository = repository;
        this.redisSync = redisSync;
        this.l2FeedService = l2FeedService;
    }

    public static class LatencyTimeoutException extends RuntimeException {
        public LatencyTimeoutException(String message) {
            super(message);
        }
    }

    @Override
    public void executeTrade(ExecutionRequest request, StreamObserver<ExecutionResponse> responseObserver) {
        executionTimer.record(() -> {
            long startTime = System.nanoTime();
            UUID signalId = UUID.fromString(request.getSignalId());

            // 1. Idempotency Check
            Boolean alreadyProcessing = redisSync.exists(signalId).block();
            if (Boolean.TRUE.equals(alreadyProcessing)) {
                logger.warn("Duplicate request detected for {}. Returning existing status.", signalId);
                String status = redisSync.getStatus(signalId).block();
                
                responseObserver.onNext(ExecutionResponse.newBuilder()
                        .setSignalId(request.getSignalId())
                        .setStatus(parseStatus(status))
                        .setMessage("Duplicate request - returning cached status")
                        .build());
                responseObserver.onCompleted();
                return;
            }

            try {
                // 2. Latency Check
                long nowNs = System.nanoTime();
                if (nowNs - request.getTimestampNs() > 50_000_000L) { // 50ms
                    throw new LatencyTimeoutException("Stale Alpha - Latency too high");
                }

                // 2. Mark in-flight in Redis
                redisSync.markInFlight(signalId, "PENDING").block();

                // 3. Process Legs
                ExecutionResponse.Builder responseBuilder = ExecutionResponse.newBuilder()
                        .setSignalId(request.getSignalId());

                // For simplicity in MVP, we calculate for the first leg
                ExecutionRequest.ExecutionLeg protoLeg = request.getLegs(0);
                ExecutionLeg.Side side = (protoLeg.getSide() == Side.SIDE_BUY) ? ExecutionLeg.Side.BUY : ExecutionLeg.Side.SELL;
                BigDecimal requestedQty = new BigDecimal(String.valueOf(protoLeg.getQuantity()));
                BigDecimal targetPrice = new BigDecimal(String.valueOf(protoLeg.getTargetPrice()));
                BigDecimal maxSlippage = new BigDecimal(String.valueOf(request.getMaxSlippagePct()));

                L2OrderBook book = l2FeedService.getLatestBook(protoLeg.getTicker());
                BigDecimal actualVwap = vwapCalculator.calculateVwap(book, side, requestedQty);

                // 4. Slippage Guard
                slippageGuard.validateSlippage(side, actualVwap, targetPrice, maxSlippage);

                // 5. Successful Logic (Execute with Broker)
                logger.info("Trade Approved. VWAP: {}. Sending to broker...", actualVwap);
                
                // ... Broker Integration ...

                responseBuilder.setStatus(ExecutionStatus.STATUS_SUCCESS)
                        .setActualVwap(actualVwap.doubleValue());

                // 6. Persist Audit
                repository.saveAudit(signalId, request.getPairId(), protoLeg.getTicker(), side.name(), 
                        requestedQty, targetPrice, actualVwap, "SUCCESS", 
                        (System.nanoTime() - startTime) / 1_000_000L).subscribe();

                responseBuilder.setProcessingTimeNs(System.nanoTime() - startTime);
                responseObserver.onNext(responseBuilder.build());
                responseObserver.onCompleted();

            } catch (VwapCalculator.InsufficientMarketDepthException e) {
                handleError(signalId, request, ExecutionStatus.STATUS_REJECTED_DEPTH, e.getMessage(), startTime, responseObserver);
            } catch (SlippageGuard.SlippageViolationException e) {
                handleError(signalId, request, ExecutionStatus.STATUS_REJECTED_SLIPPAGE, e.getMessage(), startTime, responseObserver);
            } catch (LatencyTimeoutException e) {
                handleError(signalId, request, ExecutionStatus.STATUS_REJECTED_LATENCY, e.getMessage(), startTime, responseObserver);
            } catch (Exception e) {
                handleError(signalId, request, ExecutionStatus.STATUS_BROKER_ERROR, e.getMessage(), startTime, responseObserver);
            }
        });
    }

    @Override
    public void getTradeStatus(TradeStatusRequest request, StreamObserver<ExecutionResponse> responseObserver) {
        UUID signalId = UUID.fromString(request.getSignalId());
        
        // Check Redis first
        String redisStatus = redisSync.getStatus(signalId).block();
        if (redisStatus != null) {
            responseObserver.onNext(ExecutionResponse.newBuilder()
                    .setSignalId(request.getSignalId())
                    .setStatus(parseStatus(redisStatus))
                    .build());
            responseObserver.onCompleted();
            return;
        }

        // Fallback to PostgreSQL
        String dbStatus = repository.getStatus(signalId).block();
        if (dbStatus != null) {
            responseObserver.onNext(ExecutionResponse.newBuilder()
                    .setSignalId(request.getSignalId())
                    .setStatus(parseStatus(dbStatus))
                    .build());
            responseObserver.onCompleted();
            return;
        }

        // Not found anywhere
        responseObserver.onNext(ExecutionResponse.newBuilder()
                .setSignalId(request.getSignalId())
                .setStatus(ExecutionStatus.STATUS_NOT_FOUND)
                .build());
        responseObserver.onCompleted();
    }

    private ExecutionStatus parseStatus(String status) {
        try {
            return ExecutionStatus.valueOf("STATUS_" + status);
        } catch (Exception e) {
            return ExecutionStatus.STATUS_BROKER_ERROR;
        }
    }

    private void handleError(UUID signalId, ExecutionRequest request, ExecutionStatus status, String msg, long startTime, StreamObserver<ExecutionResponse> responseObserver) {
        logger.error("Execution failed for {}: {}", signalId, msg);
        
        ExecutionResponse response = ExecutionResponse.newBuilder()
                .setSignalId(request.getSignalId())
                .setStatus(status)
                .setMessage(msg)
                .setProcessingTimeNs(System.nanoTime() - startTime)
                .build();

        // Async audit save
        repository.saveAudit(signalId, request.getPairId(), request.getLegs(0).getTicker(), 
                request.getLegs(0).getSide().name(), new BigDecimal(String.valueOf(request.getLegs(0).getQuantity())), 
                new BigDecimal(String.valueOf(request.getLegs(0).getTargetPrice())), BigDecimal.ZERO, status.name(), 
                (System.nanoTime() - startTime) / 1_000_000L).subscribe();

        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
