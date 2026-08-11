# Assistant Working Notes

This file is a compact repo map for assistant-style coding sessions. The runtime source of truth is the code plus the current docs under `README.md` and `docs/`.

**Process:** follow [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) (issues with `[Correção]`/`[Melhoria]`/`[Nova função]`, PRs that `Fixes #N`, Hermes via forge when online).

## What This System Is

Alpha Arbitrage is a statistical-arbitrage bot with:

- a Python monitor and dashboard API;
- a React operations console;
- a Java gRPC dry-run execution sidecar;
- Redis, PostgreSQL, and SQLite state;
- Alpaca as the active Python brokerage path (Trading 212 and Web3 remain in-repo but fail startup / legacy-disabled);
- Telegram/dashboard approval and audit paths.

Default to paper mode while changing execution logic.

## Repository Layout

| Path | Role |
|---|---|
| `src/monitor.py` | Main scan loop and execution coordination |
| `src/config.py` | Pydantic settings, pair universe, runtime overrides |
| `src/services/` | Brokerage (Alpaca active), risk, dashboard, persistence, telemetry, data |
| `src/agents/` | Signal validation ensemble |
| `src/daemons/` | Background workers |
| `frontend/` | React dashboard |
| `execution-engine/` | Java gRPC execution service |
| `infra/` | Docker and deployment wiring |
| `tests/` | Python tests |
| `.agents/` | Speckit commands/skills (engineering / quant / motion) |
| `.github/agents/` | Copilot custom agents (trading safety, review, test, ops) |
| `.specify/` and `specs/` | Feature planning templates and specs |

## Commands

### Python

Prefer locked deps + `PYTHONPATH` (or `-m`) so `src` resolves:

```bash
uv pip install -r requirements.lock
PYTHONPATH=. python scripts/init_db.py
PYTHONPATH=. python -m src.monitor
PYTHONPATH=. python src/mcp_server.py
PYTHONPATH=. pytest tests/ -v --asyncio-mode=auto
```

Focused examples:

```bash
PYTHONPATH=. pytest tests/unit/test_pair_eligibility.py -v --asyncio-mode=auto
PYTHONPATH=. pytest tests/unit/test_config_env_parsing.py -v --asyncio-mode=auto
PYTHONPATH=. pytest tests/integration/test_portfolio_orchestration.py -v --asyncio-mode=auto
```

### Frontend

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
npm run lint
npm run test
npm run build
```

### Java

There is no Gradle wrapper in the repo right now; use installed Gradle:

```bash
cd execution-engine
gradle generateProto --no-daemon
gradle shadowJar --no-daemon
gradle test --no-daemon
DRY_RUN=true gradle run --no-daemon
```

### Docker

```bash
docker compose -f infra/docker-compose.yml up -d

docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.local.yml \
  up -d --build --remove-orphans
```

Compose restart: `bot` / `sec-worker` / `frontend` / `execution-engine` → `unless-stopped`; Redis/Postgres → `always`; optional `mcp-server` → `no`.
## Key Invariants

- `POSTGRES_PASSWORD` and `DASHBOARD_TOKEN` must be non-default.
- Keep `PAPER_TRADING=true` for tests and development unless explicitly validating live paths.
- Keep `DRY_RUN=true` for the Java engine; `DRY_RUN=false` intentionally fails startup.
- Do not hardcode venue checks outside `BrokerageService.get_venue()`.
- Do not bypass the dashboard/session/2FA model when adding operator controls.
- Preserve `signal_id` through reasoning, journal, shadow/live ledger rows, and close paths.
- Use service singletons in `src/services/` where existing code already does.

## Signal Flow To Understand Before Editing

1. Pair universe is loaded and filtered by `pair_eligibility_service`.
2. Historical data warms Kalman filters and checks cointegration.
3. `process_pair()` updates Kalman state and compares z-score threshold.
4. The orchestrator validates signals with macro, bull/bear, SEC cache, whale watcher (currently `INACTIVE`), portfolio, and accuracy logic.
5. Approval is requested.
6. Paper/shadow mode uses `shadow_service`; broker Alpaca paper uses `BrokerageService` with auto-approve on the paper API.
7. Live real-money mode uses Python `BrokerageService` with Alpaca only (`BROKERAGE_PROVIDER=ALPACA`).
8. Java gRPC is available for dry-run execution/audit paths (`DRY_RUN=true` required).

## Documentation Pointers

- `README.md`: quick start and project map.
- `docs/AGENT_WORKFLOW.md`: **required** issue/PR/Hermes process + target observability/quality/test/motion stack.
- `docs/ARCHITECTURE.md`: current architecture.
- `docs/OPERATIONS.md`: runbook.
- `docs/STRATEGY.md`: signal/risk logic.
- `docs/tofix.md`: current known backlog.
- `src/README.md`, `frontend/README.md`, `execution-engine/README.md`, `infra/README.md`: per-project docs.

## Historical Files

`docs/bugs.md`, `docs/MONDAY_READINESS_AUDIT.md`, `docs/geminiplan.md`, Phase audits, and `.brain/*` are useful context, but they are historical. Check current code before treating any old finding as still open. Default branch is `master`.
