package com.arbitrage.engine.api;

import com.arbitrage.engine.core.ExecutionConstants;
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

            // 1. Atomic Idempotency Check (US1)
            String idempotencyStatus = redisSync.checkAndSetIdempotency(signalId).block();
            if (!"OK".equals(idempotencyStatus)) {
                logger.warn("Duplicate request detected for {}. Status: {}. Returning cached status.", signalId, idempotencyStatus);
                
                responseObserver.onNext(ExecutionResponse.newBuilder()
                        .setSignalId(request.getSignalId())
                        .setStatus(parseStatus(idempotencyStatus))
                        .setMessage("Duplicate request - returning cached status")
                        .build());
                responseObserver.onCompleted();
                return;
            }

            ExecutionStatus finalStatus = ExecutionStatus.STATUS_BROKER_ERROR;
            String errorMessage = null;
            BigDecimal actualVwap = BigDecimal.ZERO;

            try {
                // 2. Latency Check
                long nowNs = System.nanoTime();
                if (nowNs - request.getTimestampNs() > 50_000_000L) { // 50ms
                    throw new LatencyTimeoutException("Stale Alpha - Latency too high");
                }

                // 3. Process Legs
                ExecutionRequest.ExecutionLeg protoLeg = request.getLegs(0);
                ExecutionLeg.Side side = (protoLeg.getSide() == Side.SIDE_BUY) ? ExecutionLeg.Side.BUY : ExecutionLeg.Side.SELL;
                BigDecimal requestedQty = new BigDecimal(String.valueOf(protoLeg.getQuantity()));
                BigDecimal targetPrice = new BigDecimal(String.valueOf(protoLeg.getTargetPrice()));
                BigDecimal maxSlippage = new BigDecimal(String.valueOf(request.getMaxSlippagePct()));

                L2OrderBook book = l2FeedService.getLatestBook(protoLeg.getTicker());
                actualVwap = vwapCalculator.calculateVwap(book, side, requestedQty);

                // 4. Slippage Guard
                slippageGuard.validateSlippage(side, actualVwap, targetPrice, maxSlippage);

                // 5. Successful Logic (Execute with Broker)
                logger.info("Trade Approved. VWAP: {}. Sending to broker...", actualVwap);
                
                // ... Broker Integration ...

                finalStatus = ExecutionStatus.STATUS_SUCCESS;

            } catch (VwapCalculator.InsufficientMarketDepthException e) {
                finalStatus = ExecutionStatus.STATUS_REJECTED_DEPTH;
                errorMessage = e.getMessage();
            } catch (SlippageGuard.SlippageViolationException e) {
                finalStatus = ExecutionStatus.STATUS_REJECTED_SLIPPAGE;
                errorMessage = e.getMessage();
            } catch (LatencyTimeoutException e) {
                finalStatus = ExecutionStatus.STATUS_REJECTED_LATENCY;
                errorMessage = e.getMessage();
            } catch (Exception e) {
                finalStatus = ExecutionStatus.STATUS_BROKER_ERROR;
                errorMessage = e.getMessage();
            } finally {
                // 6. Guaranteed State Cleanup (US2)
                String terminalStatus = finalStatus.name().replace("STATUS_", "");
                redisSync.updateStatus(signalId, terminalStatus).block();

                // 7. Reliable Ledger Persistence (US3) - Blocking wait on persistence
                try {
                    repository.saveAudit(
                        signalId, 
                        request.getPairId(), 
                        request.getLegs(0).getTicker(), 
                        request.getLegs(0).getSide().name(), 
                        new BigDecimal(String.valueOf(request.getLegs(0).getQuantity())), 
                        new BigDecimal(String.valueOf(request.getLegs(0).getTargetPrice())), 
                        actualVwap, 
                        terminalStatus, 
                        (System.nanoTime() - startTime) / 1_000_000L
                    ).block(); // Blocking wait for persistence/DLQ push
                } catch (Exception e) {
                    logger.error("Failed to ensure ledger persistence for {}.", signalId, e);
                    // If even the DLQ push fails, we already have finalStatus set.
                }

                // 8. Final gRPC Response
                ExecutionResponse.Builder responseBuilder = ExecutionResponse.newBuilder()
                        .setSignalId(request.getSignalId())
                        .setStatus(finalStatus)
                        .setActualVwap(actualVwap.doubleValue())
                        .setProcessingTimeNs(System.nanoTime() - startTime);
                
                if (errorMessage != null) {
                    responseBuilder.setMessage(errorMessage);
                }

                responseObserver.onNext(responseBuilder.build());
                responseObserver.onCompleted();
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
        if (status == null) return ExecutionStatus.STATUS_NOT_FOUND;
        try {
            if (status.startsWith("STATUS_")) {
                return ExecutionStatus.valueOf(status);
            }
            return ExecutionStatus.valueOf("STATUS_" + status);
        } catch (Exception e) {
            return ExecutionStatus.STATUS_BROKER_ERROR;
        }
    }
}
