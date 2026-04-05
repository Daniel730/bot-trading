package com.arbitrage.engine;

import com.arbitrage.engine.api.ExecutionServiceImpl;
import com.arbitrage.engine.api.L2FeedService;
import com.arbitrage.engine.persistence.RedisOrderSync;
import com.arbitrage.engine.persistence.TradeLedgerRepository;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.r2dbc.postgresql.PostgresqlConnectionConfiguration;
import io.r2dbc.postgresql.PostgresqlConnectionFactory;
import io.r2dbc.pool.ConnectionPool;
import io.r2dbc.pool.ConnectionPoolConfiguration;
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.Executors;

public class Application {
    private static final Logger logger = LoggerFactory.getLogger(Application.class);
    private static final int PORT = 50051;

    public static void main(String[] args) throws IOException, InterruptedException {
        // Environment variables
        String redisUri = System.getenv().getOrDefault("REDIS_URI", "redis://localhost:6379");
        String dbHost = System.getenv().getOrDefault("DB_HOST", "localhost");
        int dbPort = Integer.parseInt(System.getenv().getOrDefault("DB_PORT", "5432"));
        String dbUser = System.getenv().getOrDefault("DB_USER", "bot_admin");
        String dbPass = System.getenv().getOrDefault("DB_PASS", "bot_pass");
        String dbName = System.getenv().getOrDefault("DB_NAME", "trading_bot");

        // Redis Setup
        RedisOrderSync redisSync = new RedisOrderSync(redisUri);
        
        // We need the raw connection for the Repository to push to DLQ
        RedisClient redisClient = RedisClient.create(redisUri);
        StatefulRedisConnection<String, String> redisConnection = redisClient.connect();

        // PostgreSQL Setup (R2DBC with Pool)
        PostgresqlConnectionConfiguration dbConfig = PostgresqlConnectionConfiguration.builder()
                .host(dbHost)
                .port(dbPort)
                .username(dbUser)
                .password(dbPass)
                .database(dbName)
                .build();
        
        PostgresqlConnectionFactory connectionFactory = new PostgresqlConnectionFactory(dbConfig);
        
        ConnectionPoolConfiguration poolConfig = ConnectionPoolConfiguration.builder(connectionFactory)
                .maxSize(20)
                .maxIdleTime(Duration.ofMinutes(30))
                .build();
        
        ConnectionPool pool = new ConnectionPool(poolConfig);

        // Repositories & Services
        TradeLedgerRepository repository = new TradeLedgerRepository(pool, redisConnection);
        L2FeedService l2FeedService = new L2FeedService(); // Placeholder, implementation depends on feed source

        ExecutionServiceImpl executionService = new ExecutionServiceImpl(repository, redisSync, l2FeedService);

        // Use Java 21 Virtual Threads for the gRPC server executor
        var executor = Executors.newVirtualThreadPerTaskExecutor();

        Server server = ServerBuilder.forPort(PORT)
                .addService(executionService)
                .executor(executor)
                .build();

        logger.info("Starting Execution Engine on port {}", PORT);
        logger.info("Using Virtual Thread Executor for high concurrency");
        logger.info("Redis: {}", redisUri);
        logger.info("PostgreSQL: {}:{}/{}", dbHost, dbPort, dbName);

        server.start();

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            logger.info("Shutting down gRPC server...");
            server.shutdown();
            redisSync.close();
            redisConnection.close();
            redisClient.shutdown();
            pool.dispose();
        }));

        server.awaitTermination();
    }
}
