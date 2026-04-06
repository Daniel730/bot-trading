package com.arbitrage.engine.api;

import com.arbitrage.engine.core.VwapCalculator;
import com.arbitrage.engine.core.models.ExecutionLeg;
import com.arbitrage.engine.config.EnvironmentConfig;
import com.arbitrage.engine.core.models.ExecutionMode;
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
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class ExecutionServiceImpl extends ExecutionServiceGrpc.ExecutionServiceImplBase {
    private static final Logger logger = LoggerFactory.getLogger(ExecutionServiceImpl.class);

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

                // 3. Process ALL Legs
                List<BigDecimal> actualVwaps = new ArrayList<>();
                List<TradeLedgerRepository.TradeAudit> audits = new ArrayList<>();
                List<Broker.BrokerLeg> brokerLegs = new ArrayList<>();
                BigDecimal maxSlippage = new BigDecimal(String.valueOf(request.getMaxSlippagePct()));
                ExecutionMode mode = EnvironmentConfig.isDryRun() ? ExecutionMode.PAPER : ExecutionMode.LIVE;

                for (ExecutionRequest.ExecutionLeg protoLeg : request.getLegsList()) {
                    ExecutionLeg.Side side = (protoLeg.getSide() == Side.SIDE_BUY) ? ExecutionLeg.Side.BUY : ExecutionLeg.Side.SELL;
                    BigDecimal requestedQty = new BigDecimal(String.valueOf(protoLeg.getQuantity()));
                    BigDecimal targetPrice = new BigDecimal(String.valueOf(protoLeg.getTargetPrice()));

                    L2OrderBook book = l2FeedService.getLatestBook(protoLeg.getTicker());
                    BigDecimal actualVwap = vwapCalculator.calculateVwap(book, side, requestedQty);

                    // 4. Slippage Guard (All-or-Nothing)
                    slippageGuard.validateSlippage(side, actualVwap, targetPrice, maxSlippage);
                    
                    actualVwaps.add(actualVwap);
                    brokerLegs.add(new Broker.BrokerLeg(protoLeg.getTicker(), side, requestedQty, actualVwap));
                    audits.add(new TradeLedgerRepository.TradeAudit(
                            protoLeg.getTicker(),
                            side.name(),
                            requestedQty,
                            targetPrice,
                            actualVwap,
                            mode,
                            "VWAP calculated from L2 OrderBook"
                    ));
                }

                // 5. Successful Logic (Execute with Broker)
                // If we reach here, ALL legs passed validation.
                logger.info("Atomic Trade Approved for {} legs. Sending to broker...", request.getLegsCount());
                
                Broker.BrokerExecutionRequest brokerRequest = new Broker.BrokerExecutionRequest(
                        signalId,
                        request.getPairId(),
                        brokerLegs
                );

                broker.execute(brokerRequest).subscribe(brokerResponse -> {
                    ExecutionResponse.Builder responseBuilder = ExecutionResponse.newBuilder()
                            .setSignalId(request.getSignalId());

                    if (brokerResponse.success()) {
                        responseBuilder.setStatus(ExecutionStatus.STATUS_SUCCESS);
                        if (!actualVwaps.isEmpty()) {
                            responseBuilder.setActualVwap(actualVwaps.get(0).doubleValue());
                        }
                        repository.saveAudits(signalId, request.getPairId(), audits, "SUCCESS", 
                                (System.nanoTime() - startTime) / 1_000_000L).subscribe();
                    } else {
                        responseBuilder.setStatus(ExecutionStatus.STATUS_BROKER_ERROR)
                                .setMessage(brokerResponse.message());
                        repository.saveAudits(signalId, request.getPairId(), audits, "BROKER_ERROR", 
                                (System.nanoTime() - startTime) / 1_000_000L).subscribe();
                    }

                    responseBuilder.setProcessingTimeNs(System.nanoTime() - startTime);
                    responseObserver.onNext(responseBuilder.build());
                    responseObserver.onCompleted();
                }, error -> {
                    handleError(signalId, request, ExecutionStatus.STATUS_BROKER_ERROR, error.getMessage(), startTime, responseObserver);
                });

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

        // Persist Audit for all legs with current failure status
        List<TradeLedgerRepository.TradeAudit> audits = new ArrayList<>();
        ExecutionMode mode = EnvironmentConfig.isDryRun() ? ExecutionMode.PAPER : ExecutionMode.LIVE;
        for (ExecutionRequest.ExecutionLeg leg : request.getLegsList()) {
            audits.add(new TradeLedgerRepository.TradeAudit(
                    leg.getTicker(),
                    leg.getSide().name(),
                    new BigDecimal(String.valueOf(leg.getQuantity())),
                    new BigDecimal(String.valueOf(leg.getTargetPrice())),
                    BigDecimal.ZERO,
                    mode,
                    "Error: " + msg
            ));
        }

        repository.saveAudits(signalId, request.getPairId(), audits, status.name(), 
                (System.nanoTime() - startTime) / 1_000_000L).subscribe();

        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
