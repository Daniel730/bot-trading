# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This System Is

Alpha Arbitrage Elite is an institutional-grade statistical arbitrage trading engine. It detects cointegrated price divergences between correlated equity pairs using Kalman filtering, validates signals through a LangGraph multi-agent AI swarm (Bull/Bear/Macro/Portfolio agents), and executes trades via a Java gRPC execution engine connected to the Trading 212 API.

The "Centaur" philosophy: humans set strategy narratives and beacon assets; the bot executes math and risk management.

---

## Commands

### Python Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database schema
python scripts/init_db.py

# Start the main arbitrage monitor loop
python src/monitor.py

# Start the FastAPI SSE telemetry server (MCP server)
python src/mcp_server.py

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/unit/test_slippage_guard.py -v

# Run a single test by name
pytest tests/unit/test_drip_safety.py::test_name -v

# Run with async support (required for many tests)
pytest tests/ -v --asyncio-mode=auto
```

### Java Execution Engine

```bash
cd execution-engine

# Generate gRPC Java stubs from .proto files (required before first build)
./gradlew generateProto --no-daemon

# Build fat JAR
./gradlew shadowJar --no-daemon

# Run tests
./gradlew test --no-daemon

# Run the execution engine directly
java -jar build/libs/execution-engine-1.0-SNAPSHOT-all.jar
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # Dev server on :5173
npm run build    # TypeScript + Vite bundle
npm run lint     # ESLint
npm run test     # Vitest
```

### Docker (Full Stack)

```bash
# Start backend infrastructure (Redis, Postgres, bot, execution engine, SEC worker)
docker-compose -f docker-compose.backend.yml up

# Start frontend
docker-compose -f docker-compose.frontend.yml up

# View logs
docker logs -f trading-bot
```

---

## Architecture

### Signal Generation Flow

1. **Data Ingestion** (`data_service.py`): Real-time prices from yfinance/Polygon API with bid-ask spreads
2. **Kalman Filtering** (`kalman_service.py`): Recursive hedge ratio estimation (delta=1e-5, R=0.001)
3. **Z-Score Trigger**: Signal fires when |z_score| > 2.0
4. **Agent Swarm Debate** (`src/agents/`): Bull/Bear/Macro/Portfolio agents vote; result goes to orchestrator
5. **Approval Gate**: Telegram human-in-the-loop if confidence above threshold
6. **Execution**: gRPC call to Java engine → broker API or shadow simulation

### Component Map

| Component | Location | Role |
|---|---|---|
| Main loop | `src/monitor.py` | Continuous arbitrage scanning |
| Config | `src/config.py` | Pydantic Settings; 21 equity pairs + crypto test pairs |
| Agent orchestrator | `src/agents/orchestrator.py` | Master coordinator; fail-fast on macro regime |
| Execution client | `src/services/execution_service_client.py` | gRPC client to Java engine (localhost:50051) |
| Telemetry API | `src/mcp_server.py` | FastAPI + SSE streaming to React dashboard |
| Java gRPC server | `execution-engine/src/main/java/com/arbitrage/engine/` | Atomic trade execution, VWAP, slippage guard |
| Dashboard | `frontend/src/App.tsx` | React 19 real-time monitoring UI |
| SEC daemon | `src/daemons/sec_fundamental_worker.py` | Background fundamental data (EDGAR, 24h Redis TTL) |

### Risk Management Layers (in execution order)

1. **Cluster Guard**: Sector exposure capped at 30% (`MAX_SECTOR_EXPOSURE`)
2. **Spread Guard**: Bid-ask spread must be < 0.3%
3. **Fee Friction Check**: Total cost < `MAX_FRICTION_PCT` (1.5%)
4. **Kelly Criterion**: Position size = kelly_f × 0.25 fractional
5. **Drawdown Circuit Breaker**: Kill switch at `MAX_DRAWDOWN` (10%)
6. **Slippage Guard** (Java): Rejects order if slippage exceeds threshold
7. **Idempotency** (Redis): Deduplication in execution engine prevents double fills
8. **Latency Budget**: Hard 50ms gRPC deadline; alarm at 1.0ms threshold

### State Persistence

- **Redis**: Kalman state matrices, current prices, L2 entropy baselines, idempotency keys (TTL-based)
- **PostgreSQL**: `TradeLedger`, `FillAnalysis`, `AgentReasoning`, `AgentPerformance`, `MarketRegime`
- **SQLite** (`logs/trading_bot.db`): Fallback/legacy

### Operation Modes

Set in `.env` (copy from `.env.template`):

- `PAPER_TRADING=true` — Shadow mode with realistic slippage penalties; no real orders sent
- `DEV_MODE=true` — Enables 24/7 crypto pair testing (BTC-USD, ETH-USD) bypassing NYSE hours (9:30–16:00 ET)
- `DRY_RUN=true` — Execution engine skips actual broker API calls
- `LIVE_CAPITAL_DANGER=true` — Bot refuses to boot if L2 entropy baselines are missing from Redis

### gRPC Proto

The `.proto` file lives in `execution-engine/src/main/proto/`. Python stubs are pre-generated in `src/generated/`. If the proto changes, regenerate both:
- Java: `./gradlew generateProto`
- Python: `python -m grpc_tools.protoc ...` (see existing generated stubs for flags)

### Frontend Authentication

Dashboard access requires `DASHBOARD_TOKEN` passed as a URL query param. The React app (`frontend/src/`) connects to the MCP server via SSE at `/api/sse` and WebSocket for risk alerts.
