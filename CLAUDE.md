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

---

## Claude Workspace (`.claude/`, `.mcp.json`)

The project's AI-assistant configuration was migrated from Gemini CLI (`.gemini/`) into Claude Code on 2026-04-19. The `.gemini/` tree is kept in place for backward compatibility, but `.claude/` is now the source of truth when working through Claude.

### Slash commands (`.claude/commands/*.md`)

Twelve commands are installed, preserving their original dotted names so existing muscle memory still works:

**Speckit workflow** (ported from the GitHub `spec-kit` Gemini templates):
- `/speckit.constitution` — Create or update the project constitution in `.specify/memory/constitution.md`.
- `/speckit.specify` — Turn a natural-language feature description into `specs/NNN-feature/spec.md` (creates the feature branch via `.specify/scripts/bash/create-new-feature.sh`).
- `/speckit.clarify` — Ask up to 5 targeted questions and encode the answers back into the spec.
- `/speckit.plan` — Generate design artifacts (plan, data-model, research, quickstart) from the spec.
- `/speckit.tasks` — Produce a dependency-ordered `tasks.md`.
- `/speckit.implement` — Execute the tasks against the plan.
- `/speckit.analyze` — Non-destructive cross-artifact consistency/quality audit of spec + plan + tasks.
- `/speckit.checklist` — Generate a tailored requirement-quality checklist for the active feature.
- `/speckit.taskstoissues` — Convert the generated tasks into GitHub Issues on the active remote.
- `/speckit.research [ticker_a] [ticker_b]` — Create `specs/{branch}/research-A-B.md` using the `research-pair` template.

**Project-specific commands:**
- `/dev.audit` — Runs `scripts/cli_audit.py` and explains architectural improvements against the Senior Developer guidelines.
- `/invest.analyze [ticker_a] [ticker_b]` — Runs `scripts/cli_analyze.py` and evaluates the pair against the Senior Investor guidelines (cointegration, correlation, liquidity).

Argument placeholders in every command were rewritten to Claude's conventions: `{{args}}` → `$ARGUMENTS`, `{{arg1}}` → `$1`, `{{arg2}}` → `$2`.

### Skills (`.claude/skills/`)

- **`financial-investor`** — Senior Quantitative Investor persona for new-pair research, risk audits, and alpha identification. Enforces the 5%-per-pair risk cap, >0.85 correlation requirement, and SEC-filing scrutiny (`src/services/sec_service.py`).
- **`senior-developer`** — Elite Software Engineer persona enforcing strict typing, async-first I/O (`asyncio` + `FastMCP`), `tenacity` retries, `pydantic` input validation, and `src/services/` singleton pattern.

Claude auto-discovers skills by name — mention a relevant trigger in the prompt (e.g. "audit this new pair") and the skill can be invoked explicitly with the Skill tool.

### MCP server (`.mcp.json`)

The project-level `.mcp.json` exposes the local `src/mcp_server.py` (FastMCP/SSE telemetry) to Claude Code. It is launched via `uv run --with fastmcp fastmcp run src/mcp_server.py` from the project root, matching the original `.gemini/settings.json` wiring but with a portable relative path.

### Speckit framework

The agent-agnostic `.specify/` directory (templates, scripts, `extensions.yml`, `memory/constitution.md`) is used verbatim by both the Speckit slash commands and any ad-hoc prompts — no migration needed.

---

## Claude Workspace (`.claude/`, `.mcp.json`)

The project's AI-assistant configuration was migrated from Gemini CLI (`.gemini/`) into Claude Code on 2026-04-19. The `.gemini/` tree is kept in place for backward compatibility, but `.claude/` is now the source of truth when working through Claude.

### Slash commands (`.claude/commands/*.md`)

Twelve commands are installed, preserving their original dotted names so existing muscle memory still works:

**Speckit workflow** (ported from the GitHub `spec-kit` Gemini templates):
- `/speckit.constitution` — Create or update the project constitution in `.specify/memory/constitution.md`.
- `/speckit.specify` — Turn a natural-language feature description into `specs/NNN-feature/spec.md` (creates the feature branch via `.specify/scripts/bash/create-new-feature.sh`).
- `/speckit.clarify` — Ask up to 5 targeted questions and encode the answers back into the spec.
- `/speckit.plan` — Generate design artifacts (plan, data-model, research, quickstart) from the spec.
- `/speckit.tasks` — Produce a dependency-ordered `tasks.md`.
- `/speckit.implement` — Execute the tasks against the plan.
- `/speckit.analyze` — Non-destructive cross-artifact consistency/quality audit of spec + plan + tasks.
- `/speckit.checklist` — Generate a tailored requirement-quality checklist for the active feature.
- `/speckit.taskstoissues` — Convert the generated tasks into GitHub Issues on the active remote.
- `/speckit.research [ticker_a] [ticker_b]` — Create `specs/{branch}/research-A-B.md` using the `research-pair` template.

**Project-specific commands:**
- `/dev.audit` — Runs `scripts/cli_audit.py` and explains architectural improvements against the Senior Developer guidelines.
- `/invest.analyze [ticker_a] [ticker_b]` — Runs `scripts/cli_analyze.py` and evaluates the pair against the Senior Investor guidelines (cointegration, correlation, liquidity).

Argument placeholders in every command were rewritten to Claude's conventions: `{{args}}` → `$ARGUMENTS`, `{{arg1}}` → `$1`, `{{arg2}}` → `$2`.

### Skills (`.claude/skills/`)

- **`financial-investor`** — Senior Quantitative Investor persona for new-pair research, risk audits, and alpha identification. Enforces the 5%-per-pair risk cap, >0.85 correlation requirement, and SEC-filing scrutiny (`src/services/sec_service.py`).
- **`senior-developer`** — Elite Software Engineer persona enforcing strict typing, async-first I/O (`asyncio` + `FastMCP`), `tenacity` retries, `pydantic` input validation, and `src/services/` singleton pattern.

Claude auto-discovers skills by name — mention a relevant trigger in the prompt (e.g. "audit this new pair") and the skill can be invoked explicitly with the Skill tool.

### MCP server (`.mcp.json`)

The project-level `.mcp.json` exposes the local `src/mcp_server.py` (FastMCP/SSE telemetry) to Claude Code. It is launched via `uv run --with fastmcp fastmcp run src/mcp_server.py` from the project root, matching the original `.gemini/settings.json` wiring but with a portable relative path.

### Speckit framework

The agent-agnostic `.specify/` directory (templates, scripts, `extensions.yml`, `memory/constitution.md`) is used verbatim by both the Speckit slash commands and any ad-hoc prompts — no migration needed.
