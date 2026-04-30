# Assistant Working Notes

This file is a compact repo map for assistant-style coding sessions. The runtime source of truth is the code plus the current docs under `README.md` and `docs/`.

## What This System Is

Alpha Arbitrage is a statistical-arbitrage bot with:

- a Python monitor and dashboard API;
- a React operations console;
- a Java gRPC dry-run execution sidecar;
- Redis, PostgreSQL, and SQLite state;
- Trading 212 and Web3 brokerage paths from Python;
- Telegram/dashboard approval and audit paths.

Default to paper mode while changing execution logic.

## Repository Layout

| Path | Role |
|---|---|
| `src/monitor.py` | Main scan loop and execution coordination |
| `src/config.py` | Pydantic settings, pair universe, runtime overrides |
| `src/services/` | Brokerage, risk, dashboard, persistence, telemetry, data, Web3 |
| `src/agents/` | Signal validation ensemble |
| `src/daemons/` | Background workers |
| `frontend/` | React dashboard |
| `execution-engine/` | Java gRPC execution service |
| `infra/` | Docker and deployment wiring |
| `tests/` | Python tests |
| `.gemini/` | Gemini command/skill artifacts kept in this repo |
| `.specify/` and `specs/` | Feature planning templates and specs |

## Commands

### Python

```bash
pip install -r requirements.txt
python scripts/init_db.py
python src/monitor.py
python src/mcp_server.py
pytest tests/ -v --asyncio-mode=auto
```

Focused examples:

```bash
pytest tests/unit/test_pair_eligibility.py -v --asyncio-mode=auto
pytest tests/unit/test_config_env_parsing.py -v --asyncio-mode=auto
pytest tests/integration/test_portfolio_orchestration.py -v --asyncio-mode=auto
```

### Frontend

```bash
cd frontend
npm install
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

## Key Invariants

- `POSTGRES_PASSWORD` and `DASHBOARD_TOKEN` must be non-default.
- Keep `PAPER_TRADING=true` for tests and development unless explicitly validating live paths.
- Keep `DRY_RUN=true` for the Java engine; `DRY_RUN=false` intentionally fails startup.
- Do not hardcode venue checks outside `BrokerageService.get_venue()`.
- Do not bypass the dashboard/session/2FA model when adding operator controls.
- Do not submit a live Trading 212 sell leg without the available-share preflight.
- Preserve `signal_id` through reasoning, journal, shadow/live ledger rows, and close paths.
- Use service singletons in `src/services/` where existing code already does.

## Signal Flow To Understand Before Editing

1. Pair universe is loaded and filtered by `pair_eligibility_service`.
2. Historical data warms Kalman filters and checks cointegration.
3. `process_pair()` updates Kalman state and compares z-score threshold.
4. The orchestrator validates signals with macro, bull/bear, SEC cache, whale watcher, portfolio, and accuracy logic.
5. Approval is requested.
6. Paper mode uses `shadow_service`.
7. Live mode uses Python `BrokerageService` for T212/Web3.
8. Java gRPC is available for dry-run execution/audit paths.

## Documentation Pointers

- `README.md`: quick start and project map.
- `docs/ARCHITECTURE.md`: current architecture.
- `docs/OPERATIONS.md`: runbook.
- `docs/STRATEGY.md`: signal/risk logic.
- `docs/tofix.md`: current known backlog.
- `src/README.md`, `frontend/README.md`, `execution-engine/README.md`, `infra/README.md`: per-project docs.

## Historical Files

`docs/bugs.md`, `docs/MONDAY_READINESS_AUDIT.md`, and `docs/geminiplan.md` are useful context, but they are historical. Check current code before treating any old finding as still open.
