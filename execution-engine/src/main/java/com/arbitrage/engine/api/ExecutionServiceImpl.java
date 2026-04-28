package com.arbitrage.engine.api;

import com.arbitrage.engine.core.VwapCalculator;
import com.arbitrage.engine.core.models.ExecutionLeg;
import com.arbitrage.engine.config.EnvironmentConfig;
import com.arbitrage.engine.core.models.ExecutionMode;
import com.arbitrage.engine.core.models.L2OrderBook;
import com.arbitrage.engine.broker.Broker;
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
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExecutionServiceImpl extends ExecutionServiceGrpc.ExecutionServiceImplBase {
    private static final Logger logger = LoggerFactory.getLogger(ExecutionServiceImpl.class);

    private final AtomicBoolean killSwitchActive = new AtomicBoolean(false);
    private final VwapCalculator vwapCalculator = new VwapCalculator();
    private final SlippageGuard slippageGuard = new SlippageGuard();
    private final TradeLedgerRepository repository;
    private final RedisOrderSync redisSync;
    private final L2FeedService l2FeedService;
    private final Broker broker;
    private final Timer executionTimer = Timer.builder("execution.latency")
            .description("Time taken for execution loop")
            .publishPercentiles(0.5, 0.9, 0.95, 0.99)
            .register(Metrics.globalRegistry);

    public ExecutionServiceImpl(TradeLedgerRepository repository, RedisOrderSync redisSync, L2FeedService l2FeedService, Broker broker) {
        this.repository = repository;
        this.redisSync = redisSync;
        this.l2FeedService = l2FeedService;
        this.broker = broker;
    }

    public static class LatencyTimeoutException extends RuntimeException {
        public LatencyTimeoutException(String message) {
            super(message);
        }
    }

    @Override
    public void executeTrade(ExecutionRequest request, StreamObserver<ExecutionResponse> responseObserver) {
        AtomicBoolean responded = new AtomicBoolean(false);
        if (killSwitchActive.get()) {
            logger.warn("Trade rejected - Kill Switch Active: {}", request.getSignalId());
            responseObserver.onNext(ExecutionResponse.newBuilder()
                    .setSignalId(request.getSignalId())
                    .setStatus(ExecutionStatus.STATUS_HALTED)
                    .setMessage("Execution Engine is HALTED via Kill Switch")
                    .build());
            responseObserver.onCompleted();
            return;
        }

        UUID signalId;
        try {
            signalId = UUID.fromString(request.getSignalId());
        } catch (IllegalArgumentException e) {
            sendOnce(responded, responseObserver, ExecutionResponse.newBuilder()
                    .setSignalId(request.getSignalId())
                    .setStatus(ExecutionStatus.STATUS_BROKER_ERROR)
                    .setMessage("Invalid signal_id UUID")
                    .build());
            return;
        }
        if (request.getLegsCount() == 0) {
            sendOnce(responded, responseObserver, ExecutionResponse.newBuilder()
                    .setSignalId(request.getSignalId())
                    .setStatus(ExecutionStatus.STATUS_BROKER_ERROR)
                    .setMessage("Execution request must contain at least one leg")
                    .build());
            return;
        }
        long startTime = System.nanoTime();
        logger.info("executeTrade: signal_id={} client_order_id={}", signalId, request.getClientOrderId());

        // 1. Idempotency Check & Reactive Pipeline
        redisSync.checkAndMarkInFlight(signalId, "PENDING", 3600)
            .flatMap(redisStatus -> {
                if (!"NEW".equals(redisStatus)) {
                    logger.warn("Duplicate request detected for {}. Status was: {}", signalId, redisStatus);
                    return Mono.just(ExecutionResponse.newBuilder()
                            .setSignalId(request.getSignalId())
                            .setStatus(parseStatus(redisStatus))
                            .setMessage("Duplicate request - returning existing status")
                            .build());
                }

                // 2. Latency Check
                long nowNs = System.nanoTime();
                if (nowNs - request.getTimestampNs() > 50_000_000L) { // 50ms
                    return Mono.error(new LatencyTimeoutException("Stale Alpha - Latency too high"));
                }

                // 3. Process ALL Legs
                List<BigDecimal> actualVwaps = new ArrayList<>();
                List<TradeLedgerRepository.TradeAudit> audits = new ArrayList<>();
                List<Broker.BrokerLeg> brokerLegs = new ArrayList<>();
                BigDecimal maxSlippage = new BigDecimal(request.getMaxSlippagePct());
                ExecutionMode mode = EnvironmentConfig.isDryRun() ? ExecutionMode.PAPER : ExecutionMode.LIVE;

                for (ExecutionRequest.ExecutionLeg protoLeg : request.getLegsList()) {
                    ExecutionLeg.Side side = (protoLeg.getSide() == Side.SIDE_BUY) ? ExecutionLeg.Side.BUY : ExecutionLeg.Side.SELL;
                    BigDecimal requestedQty = new BigDecimal(protoLeg.getQuantity());
                    BigDecimal targetPrice = new BigDecimal(protoLeg.getTargetPrice());
                    if (requestedQty.signum() <= 0 || targetPrice.signum() <= 0) {
                        return Mono.error(new IllegalArgumentException("Leg quantity and target price must be positive for " + protoLeg.getTicker()));
                    }

                    L2OrderBook book = l2FeedService.getLatestBook(protoLeg.getTicker());
                    if (book == null) {
                        return Mono.error(new VwapCalculator.InsufficientMarketDepthException("No L2 Book data available for " + protoLeg.getTicker()));
                    }
                    BigDecimal actualVwap = vwapCalculator.calculateVwap(book, side, requestedQty);

                    // 4. Slippage Guard (All-or-Nothing)
                    try {
                        slippageGuard.validateSlippage(side, actualVwap, targetPrice, maxSlippage);
                    } catch (SlippageGuard.SlippageViolationException e) {
                        return Mono.error(e);
                    }
                    
                    actualVwaps.add(actualVwap);
                    brokerLegs.add(new Broker.BrokerLeg(protoLeg.getTicker(), side, requestedQty, actualVwap));
                    
                    String l2SnapshotJson = book.toJson(); 
                    
                    audits.add(new TradeLedgerRepository.TradeAudit(
                            protoLeg.getTicker(),
                            side.name(),
                            requestedQty,
                            targetPrice,
                            actualVwap,
                            mode,
                            "{\"strategy\": \"VWAP\", \"l2_snapshot\": " + l2SnapshotJson + "}"
                    ));
                }

                // 5. Successful Logic (Execute with Broker)
                logger.info("Atomic Trade Approved for {} legs. Sending to broker...", request.getLegsCount());
                
                Broker.BrokerExecutionRequest brokerRequest = new Broker.BrokerExecutionRequest(
                        signalId,
                        request.getPairId(),
                        brokerLegs
                );

                return broker.execute(brokerRequest)
                    .flatMap(brokerResponse -> {
                        ExecutionResponse.Builder responseBuilder = ExecutionResponse.newBuilder()
                                .setSignalId(request.getSignalId());

                        String finalStatus;
                        if (brokerResponse.success()) {
                            responseBuilder.setStatus(ExecutionStatus.STATUS_SUCCESS);
                            if (!actualVwaps.isEmpty()) {
                                responseBuilder.setActualVwap(actualVwaps.get(0).toPlainString());
                            }
                            finalStatus = "SUCCESS";
                        } else {
                            responseBuilder.setStatus(ExecutionStatus.STATUS_BROKER_ERROR)
                                    .setMessage(brokerResponse.message());
                            finalStatus = "BROKER_ERROR";
                        }

                        responseBuilder.setProcessingTimeNs(System.nanoTime() - startTime);
                        ExecutionResponse finalResponse = responseBuilder.build();

                        return repository.saveAudits(signalId, request.getPairId(), audits, finalStatus, 
                                (System.nanoTime() - startTime) / 1_000_000L)
                            .thenReturn(finalResponse);
                    });
            })
            .subscribe(response -> {
                sendOnce(responded, responseObserver, response);
            }, error -> {
                ExecutionStatus failedStatus = ExecutionStatus.STATUS_BROKER_ERROR;
                if (error instanceof VwapCalculator.InsufficientMarketDepthException) failedStatus = ExecutionStatus.STATUS_REJECTED_DEPTH;
                else if (error instanceof SlippageGuard.SlippageViolationException) failedStatus = ExecutionStatus.STATUS_REJECTED_SLIPPAGE;
                else if (error instanceof LatencyTimeoutException) failedStatus = ExecutionStatus.STATUS_REJECTED_LATENCY;

                handleError(signalId, request, failedStatus, error.getMessage(), startTime, responseObserver, responded);
            });
    }

    @Override
    public void getTradeStatus(TradeStatusRequest request, StreamObserver<ExecutionResponse> responseObserver) {
        UUID signalId;
        try {
            signalId = UUID.fromString(request.getSignalId());
        } catch (IllegalArgumentException e) {
            responseObserver.onNext(ExecutionResponse.newBuilder()
                    .setSignalId(request.getSignalId())
                    .setStatus(ExecutionStatus.STATUS_BROKER_ERROR)
                    .setMessage("Invalid signal_id UUID")
                    .build());
            responseObserver.onCompleted();
            return;
        }
        
        // Check Redis first, then PostgreSQL
        redisSync.getStatus(signalId)
            .flatMap(redisStatus -> {
                if (redisStatus != null) {
                    return Mono.just(ExecutionResponse.newBuilder()
                            .setSignalId(request.getSignalId())
                            .setStatus(parseStatus(redisStatus))
                            .build());
                }
                // Fallback to PostgreSQL
                return repository.getStatus(signalId)
                    .map(dbStatus -> ExecutionResponse.newBuilder()
                            .setSignalId(request.getSignalId())
                            .setStatus(parseStatus(dbStatus))
                            .build())
                    .defaultIfEmpty(ExecutionResponse.newBuilder()
                            .setSignalId(request.getSignalId())
                            .setStatus(ExecutionStatus.STATUS_NOT_FOUND)
                            .build());
            })
            .subscribe(response -> {
                responseObserver.onNext(response);
                responseObserver.onCompleted();
            }, error -> {
                logger.error("Error fetching trade status for {}: {}", signalId, error.getMessage());
                responseObserver.onError(error);
            });
    }

    @Override
    public void triggerKillSwitch(KillSwitchRequest request, StreamObserver<KillSwitchResponse> responseObserver) {
        logger.warn("!!! KILL SWITCH TRIGGERED !!! Reason: {}", request.getReason());
        killSwitchActive.set(true);

        int cancelled = broker.cancelAllOrders();
        int liquidated = 0;

        if (request.getLiquidate()) {
            logger.warn("EMERGENCY LIQUIDATION INITIATED...");
            liquidated = broker.liquidateAllPositions();
        }

        responseObserver.onNext(KillSwitchResponse.newBuilder()
                .setSuccess(true)
                .setStatusMessage("System Halted. Kill Switch Active.")
                .setOrdersCancelled(cancelled)
                .setPositionsLiquidated(liquidated)
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

    private void sendOnce(AtomicBoolean responded, StreamObserver<ExecutionResponse> responseObserver, ExecutionResponse response) {
        if (responded.compareAndSet(false, true)) {
            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } else {
            logger.warn("Suppressing duplicate gRPC terminal response for signal {}", response.getSignalId());
        }
    }

    private void handleError(UUID signalId, ExecutionRequest request, ExecutionStatus status, String msg, long startTime, StreamObserver<ExecutionResponse> responseObserver, AtomicBoolean responded) {
        logger.error("Execution failed for {}: {}", signalId, msg);
        
        ExecutionResponse response = ExecutionResponse.newBuilder()
                .setSignalId(request.getSignalId())
                .setStatus(status)
                .setMessage(msg)
                .setProcessingTimeNs(System.nanoTime() - startTime)
                .build();

        // Persist Audit for all legs with current failure status
        List<TradeLedgerRepository.TradeAudit> audits = new ArrayList<>();
        ExecutionMode mode = EnvironmentConfig.isDryRun() ? ExecutionMode.PAPER : ExecutionMode.LIVE;
        for (ExecutionRequest.ExecutionLeg leg : request.getLegsList()) {
            BigDecimal requestedQty;
            BigDecimal targetPrice;
            try {
                requestedQty = new BigDecimal(leg.getQuantity());
                targetPrice = new BigDecimal(leg.getTargetPrice());
            } catch (NumberFormatException e) {
                requestedQty = BigDecimal.ZERO;
                targetPrice = BigDecimal.ZERO;
            }
            audits.add(new TradeLedgerRepository.TradeAudit(
                    leg.getTicker(),
                    leg.getSide().name(),
                    requestedQty,
                    targetPrice,
                    BigDecimal.ZERO,
                    mode,
                    "Error: " + msg
            ));
        }

        // J-04: Add error handler — bare subscribe() silently drops exceptions.
        // Note: saveAudits returns Mono<Void>; onBackpressureBuffer is a Flux-only operator
        // and would not compile here (a Mono emits at most one item, so there is no
        // backpressure to buffer). The onErrorResume guard is what we actually need.
        repository.saveAudits(signalId, request.getPairId(), audits, status.name(),
                (System.nanoTime() - startTime) / 1_000_000L)
            .subscribe(
                null,
                err -> logger.error("Audit persist failed for signal {}: {}", signalId, err.getMessage())
            );

        sendOnce(responded, responseObserver, response);
    }
}
