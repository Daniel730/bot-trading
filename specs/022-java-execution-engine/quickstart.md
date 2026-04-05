# Quickstart: High-Performance Execution Engine (The Muscle)

## Prerequisites
*   Java 21 JDK installed.
*   Gradle 8.x installed (optional, use `./gradlew` instead).
*   Docker & Docker Compose (for PostgreSQL/Redis dependencies).

## 1. Setup Environment
Ensure the local infrastructure is running:
```bash
docker-compose up -d postgres redis
```

## 2. Build and Generate Proto
Run the Gradle build to compile the Java code and generate the gRPC classes from `execution.proto`:
```bash
cd execution-engine
./gradlew build
```

## 3. Run the Service
Start the Execution Engine locally:
```bash
./gradlew run
```
The server will start on port `50051` (default).

## 4. Test Connectivity (gRPCurl)
You can test the service using `grpcurl`:
```bash
grpcurl -plaintext -d '{
  "signal_id": "550e8400-e29b-41d4-a716-446655440000",
  "pair_id": "KO_PEP",
  "timestamp_ns": 1712345678900000000,
  "max_slippage_pct": 0.001,
  "legs": [
    {"ticker": "KO", "side": "SIDE_BUY", "quantity": 10.0, "target_price": 50.0}
  ]
}' localhost:50051 com.arbitrage.engine.ExecutionService/ExecuteTrade
```

## 5. Development Mode
To skip brokerage execution and only test the "Walk the Book" logic, set `DEV_MODE=true` in your environment.
