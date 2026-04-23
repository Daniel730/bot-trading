package com.arbitrage.engine.api;

import com.arbitrage.engine.grpc.ExecutionRequest;
import com.arbitrage.engine.grpc.ExecutionResponse;
import com.arbitrage.engine.grpc.ExecutionServiceGrpc;
import com.arbitrage.engine.grpc.ExecutionStatus;
import com.arbitrage.engine.grpc.KillSwitchRequest;
import com.arbitrage.engine.grpc.KillSwitchResponse;
import com.arbitrage.engine.grpc.TradeStatusRequest;
import io.grpc.stub.StreamObserver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Safe fallback registered on the gRPC server when the full
 * {@link ExecutionServiceImpl} dependencies (Postgres R2DBC, Lettuce Redis,
 * L2 feed, broker adapters) are not wired.
 *
 * <p>Without this, the server starts with <strong>zero services</strong>
 * registered and every RPC returns {@code UNIMPLEMENTED}. That silently
 * breaks any Python-side integration test hitting {@link ExecutionServiceImpl}
 * during paper-trading validation.
 *
 * <p>This stub returns a clean, typed {@link ExecutionStatus#STATUS_BROKER_ERROR}
 * response with a diagnostic message so Python-side error paths execute the
 * same code they would in production, while making it obvious from logs
 * that the real engine is not configured.
 *
 * <p>Added 2026-04-19 as part of Monday paper-trading readiness (R1).
 */
public class StubExecutionService extends ExecutionServiceGrpc.ExecutionServiceImplBase {
    private static final Logger logger = LoggerFactory.getLogger(StubExecutionService.class);
    private static final String NOT_CONFIGURED =
            "Execution engine is running in stub mode — real broker/DB/Redis dependencies are not wired. "
                    + "Set PAPER_TRADING=true (Python side) and do not rely on this service for live execution.";

    @Override
    public void executeTrade(ExecutionRequest request, StreamObserver<ExecutionResponse> responseObserver) {
        logger.warn(
                "StubExecutionService.executeTrade invoked for signal={} pair={} — returning STATUS_BROKER_ERROR",
                request.getSignalId(), request.getPairId());
        responseObserver.onNext(
                ExecutionResponse.newBuilder()
                        .setSignalId(request.getSignalId())
                        .setStatus(ExecutionStatus.STATUS_BROKER_ERROR)
                        .setMessage(NOT_CONFIGURED)
                        .setActualVwap("0")
                        .setProcessingTimeNs(0L)
                        .build());
        responseObserver.onCompleted();
    }

    @Override
    public void getTradeStatus(TradeStatusRequest request, StreamObserver<ExecutionResponse> responseObserver) {
        logger.warn("StubExecutionService.getTradeStatus invoked for signal={}", request.getSignalId());
        responseObserver.onNext(
                ExecutionResponse.newBuilder()
                        .setSignalId(request.getSignalId())
                        .setStatus(ExecutionStatus.STATUS_NOT_FOUND)
                        .setMessage(NOT_CONFIGURED)
                        .setActualVwap("0")
                        .setProcessingTimeNs(0L)
                        .build());
        responseObserver.onCompleted();
    }

    @Override
    public void triggerKillSwitch(KillSwitchRequest request, StreamObserver<KillSwitchResponse> responseObserver) {
        logger.error(
                "StubExecutionService.triggerKillSwitch invoked — reason='{}' liquidate={}",
                request.getReason(), request.getLiquidate());
        responseObserver.onNext(
                KillSwitchResponse.newBuilder()
                        .setSuccess(false)
                        .setStatusMessage(NOT_CONFIGURED)
                        .setOrdersCancelled(0)
                        .setPositionsLiquidated(0)
                        .build());
        responseObserver.onCompleted();
    }
}
