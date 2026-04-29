package com.arbitrage.engine;

import com.arbitrage.engine.api.ExecutionServiceImpl;
import com.arbitrage.engine.api.LatencyInterceptor;
import com.arbitrage.engine.api.RedisL2FeedService;
import com.arbitrage.engine.broker.Broker;
import com.arbitrage.engine.broker.BrokerageRouter;
import com.arbitrage.engine.config.EnvironmentConfig;
import com.arbitrage.engine.persistence.RedisOrderSync;
import com.arbitrage.engine.persistence.TradeLedgerRepository;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;
import io.r2dbc.postgresql.PostgresqlConnectionConfiguration;
import io.r2dbc.postgresql.PostgresqlConnectionFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.util.concurrent.Executors;

public class Application {
    private static final Logger logger = LoggerFactory.getLogger(Application.class);
    private static final int PORT = 50051;

    public static void main(String[] args) throws IOException, InterruptedException {
        if (EnvironmentConfig.isLiveCapitalDanger()) {
            verifyEntropyBaselines();
        }
        if (!EnvironmentConfig.isDryRun()) {
            throw new IllegalStateException(
                    "Execution engine live brokerage is not implemented. Set DRY_RUN=true or wire a real LiveBroker before enabling live mode."
            );
        }

        var executor = Executors.newVirtualThreadPerTaskExecutor();

        PostgresqlConnectionFactory connectionFactory = new PostgresqlConnectionFactory(
                PostgresqlConnectionConfiguration.builder()
                        .host(env("POSTGRES_HOST", "localhost"))
                        .port(Integer.parseInt(env("POSTGRES_PORT", "5432")))
                        .username(env("POSTGRES_USER", "bot_admin"))
                        .password(env("POSTGRES_PASSWORD", "ci_postgres_password"))
                        .database(env("POSTGRES_DB", "trading_bot"))
                        .build()
        );
        TradeLedgerRepository repository = new TradeLedgerRepository(connectionFactory);
        RedisOrderSync redisSync = new RedisOrderSync(redisUri());
        RedisL2FeedService l2FeedService = new RedisL2FeedService(redisUri());
        Broker broker = BrokerageRouter.getBroker(l2FeedService);

        Server server = ServerBuilder.forPort(PORT)
                .addService(new ExecutionServiceImpl(repository, redisSync, l2FeedService, broker))
                .intercept(new LatencyInterceptor())
                .executor(executor)
                .build();

        logger.info("Starting Execution Engine on port {}", PORT);
        logger.info("Registered ExecutionServiceImpl with repository, Redis idempotency, L2 adapter, and broker router.");
        logger.info("Using Virtual Thread Executor for high concurrency");

        server.start();

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            logger.info("Shutting down gRPC server...");
            redisSync.close();
            l2FeedService.close();
            server.shutdown();
        }));

        server.awaitTermination();
    }

    private static String env(String key, String defaultValue) {
        String value = System.getenv(key);
        return value == null || value.isBlank() ? defaultValue : value;
    }

    private static String redisUri() {
        String host = env("REDIS_HOST", "localhost");
        String port = env("REDIS_PORT", "6379");
        String password = System.getenv("REDIS_PASSWORD");
        if (password != null && !password.isBlank()) {
            return "redis://:" + password + "@" + host + ":" + port;
        }
        return "redis://" + host + ":" + port;
    }

    private static void verifyEntropyBaselines() {
        logger.info("VERIFYING L2 ENTROPY BASELINES FOR LIVE CAPITAL DANGER...");

        RedisClient redisClient = RedisClient.create(redisUri());
        try (StatefulRedisConnection<String, String> connection = redisClient.connect()) {
            RedisCommands<String, String> syncCommands = connection.sync();

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
