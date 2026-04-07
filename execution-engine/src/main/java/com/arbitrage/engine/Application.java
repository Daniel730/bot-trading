package com.arbitrage.engine;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.util.concurrent.Executors;

public class Application {
    private static final Logger logger = LoggerFactory.getLogger(Application.class);
    private static final int PORT = 50051;

    public static void main(String[] args) throws IOException, InterruptedException {
        // Use Java 21 Virtual Threads for the gRPC server executor
        var executor = Executors.newVirtualThreadPerTaskExecutor();

        Server server = ServerBuilder.forPort(PORT)
                // .addService(...) // Will add services in Phase 2
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
}
