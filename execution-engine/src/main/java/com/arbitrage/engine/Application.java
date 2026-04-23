package com.arbitrage.engine;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import com.arbitrage.engine.config.EnvironmentConfig;
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;

import java.io.IOException;
import java.util.concurrent.Executors;

public class Application {
    private static final Logger logger = LoggerFactory.getLogger(Application.class);
    private static final int PORT = 50051;

    public static void main(String[] args) throws IOException, InterruptedException {
        if (EnvironmentConfig.isLiveCapitalDanger()) {
            verifyEntropyBaselines();
        }

        // Use Java 21 Virtual Threads for the gRPC server executor
        var executor = Executors.newVirtualThreadPerTaskExecutor();

        // R1 fix (2026-04-19): Register a gRPC service so calls don't return
        // UNIMPLEMENTED. The full ExecutionServiceImpl requires a TradeLedgerRepository
        // (Postgres R2DBC), RedisOrderSync (Lettuce), L2FeedService, and a Broker —
        // none of which are wired yet. Until a DI layer exists we register a safe
        // StubExecutionService that returns typed STATUS_BROKER_ERROR responses and
        // logs every invocation. Paper trading uses Python-side shadow_service and
        // does not depend on this path, so the stub is adequate for the Monday
        // go-live test. Swap to ExecutionServiceImpl once dependencies are wired.
        io.grpc.BindableService grpcService = new com.arbitrage.engine.api.StubExecutionService();
        logger.warn("Registering StubExecutionService — real execution dependencies not wired. "
                + "This is SAFE for paper trading; DO NOT use for live capital.");

        Server server = ServerBuilder.forPort(PORT)
                .addService(grpcService)
                .intercept(new com.arbitrage.engine.api.LatencyInterceptor())
                .executor(executor)
                .build();

        logger.info("Starting Execution Engine on port {}", PORT);
        logger.info("Using Virtual Thread Executor for high concurrency");

        server.start();

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            logger.info("Shutting down gRPC server...");
            server.shutdown();
        }));

        server.awaitTermination();
    }

    private static void verifyEntropyBaselines() {
        logger.info("VERIFYING L2 ENTROPY BASELINES FOR LIVE CAPITAL DANGER...");
        
        String redisHost = System.getenv("REDIS_HOST");
        if (redisHost == null) redisHost = "localhost";
        
        RedisClient redisClient = RedisClient.create("redis://" + redisHost);
        try (StatefulRedisConnection<String, String> connection = redisClient.connect()) {
            RedisCommands<String, String> syncCommands = connection.sync();
            
            // T005: Check for critical tickers
            String[] tickers = {"KO", "PEP", "MA", "V", "XOM", "CVX"};
            boolean missing = false;
            
            for (String ticker : tickers) {
                if (syncCommands.exists("entropy_baseline:" + ticker) == 0) {
                    logger.error("CRITICAL: Missing L2 Entropy Baseline for ticker: {}", ticker);
                    missing = true;
                }
            }
            
            if (missing) {
                logger.error("SYSTEM_REFUSE: L2 Entropy Baselines missing. Refusing to boot in LIVE mode.");
                System.exit(1);
            }
            
            logger.info("L2 ENTROPY BASELINES VERIFIED. SAFETY CHECKS PASSED.");
        } finally {
            redisClient.shutdown();
        }
    }
}
