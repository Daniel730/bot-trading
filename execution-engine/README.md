# Java Execution Engine

The execution engine is the low-latency gRPC sidecar for atomic trade execution. It accepts execution requests from Python, validates L2/VWAP/slippage constraints, deduplicates retried requests through Redis, records audits in PostgreSQL, and returns a compact execution response.

## Stack

- Java 21
- Gradle Kotlin build
- gRPC / Protocol Buffers
- R2DBC PostgreSQL
- Lettuce Redis
- JUnit 5, Mockito, Testcontainers

## Important Safety State

`DRY_RUN=true` is required. `Application` intentionally refuses to boot with `DRY_RUN=false` because the real Java `LiveBroker` path is not wired for production brokerage execution yet. Live Trading 212 and Web3 execution are currently handled by the Python brokerage dispatcher.

## Build And Test

This repo does not currently include a Gradle wrapper, so use an installed `gradle` command:

```bash
gradle generateProto --no-daemon
gradle shadowJar --no-daemon
gradle test --no-daemon
```

Run locally from PowerShell:

```powershell
$env:DRY_RUN="true"
gradle run --no-daemon
```

or from bash:

```bash
DRY_RUN=true gradle run --no-daemon
```

Run the built jar from PowerShell:

```powershell
$env:DRY_RUN="true"
java -jar build/libs/execution-engine-1.0-SNAPSHOT-all.jar
```

## Runtime Env

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port inside Docker network |
| `POSTGRES_USER` | `bot_admin` | PostgreSQL user |
| `POSTGRES_PASSWORD` | `ci_postgres_password` fallback in Java | Database password; set explicitly outside tests |
| `POSTGRES_DB` | `trading_bot` | Database name |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | empty | Optional Redis password |
| `DRY_RUN` | read by `EnvironmentConfig` | Must be true until live broker wiring exists |
| `LIVE_CAPITAL_DANGER` | false | Requires Redis entropy baselines before boot |

## gRPC Surface

The proto lives at `src/main/proto/execution.proto` and exposes:

- `ExecuteTrade`
- `GetTradeStatus`
- `TriggerKillSwitch`

`ExecutionRequest.client_order_id` is the wire-level idempotency key for retries.

## Docker

```bash
docker build -t execution-engine .
docker run --rm -p 50051:50051 --env-file ../.env execution-engine
```

The production compose file uses a TCP healthcheck against port `50051` before dependent Python services begin sending gRPC calls.
