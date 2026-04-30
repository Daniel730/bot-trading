# bot-trading Development Guidelines

Last refreshed: 2026-04-30

This file orients Gemini-style assistant sessions. For the full current docs, start at `README.md` and `docs/README.md`.

## Active Technologies

- Python 3.11
- FastAPI, FastMCP, SSE, WebSocket telemetry
- pandas, numpy, scipy, statsmodels, yfinance, Polygon client
- Pydantic v2 settings
- Redis, PostgreSQL, SQLite
- gRPC Python stubs and Java gRPC service
- Java 21 with Gradle
- React 19, Vite 8, TypeScript, Vitest
- Docker Compose and GHCR images

## Project Structure

```text
src/
  monitor.py                    # main trading loop and dashboard startup
  mcp_server.py                 # optional FastMCP SSE tool server
  agents/                       # signal validation ensemble
  daemons/                      # background workers
  services/                     # risk, broker, dashboard, data, persistence
frontend/                       # React operations console
execution-engine/               # Java gRPC execution engine
infra/                          # Docker/deploy wiring
docs/                           # current docs and historical audits
tests/                          # Python tests
```

## Current Runtime Notes

- `PAPER_TRADING=true` is the safe default and routes fills through the shadow service.
- `DEV_MODE=true` is for crypto-only 24/7 development behavior and should not be used for production decisions.
- `DRY_RUN=true` is required for the Java engine because live Java brokerage is intentionally blocked.
- Dashboard API runs on port `8080`; optional FastMCP runs on port `8000`.
- Dashboard auth uses `DASHBOARD_TOKEN` plus a dashboard session; sensitive config writes require 2FA after setup.
- Pair universe and settings can be overridden at runtime through `data/pairs.json` and `data/bot_settings.json`.

## Commands

```bash
pip install -r requirements.txt
python scripts/init_db.py
python src/monitor.py
python src/mcp_server.py
pytest tests/ -v --asyncio-mode=auto
```

```bash
cd frontend
npm install
npm run dev
npm run lint
npm run test
npm run build
```

```bash
cd execution-engine
gradle generateProto --no-daemon
gradle shadowJar --no-daemon
gradle test --no-daemon
```

```bash
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml -f infra/docker-compose.local.yml up -d --build
```

## Development Rules

- Preserve `signal_id` through signal evaluation, approval, execution, journal, and close paths.
- Keep venue routing centralized in `BrokerageService.get_venue()`.
- Use async I/O or `asyncio.to_thread` around blocking APIs.
- Keep secrets out of docs, logs, and committed env files.
- When touching execution paths, run focused brokerage, risk, and persistence tests.
- When touching frontend auth/telemetry, run `npm run test` and `npm run build`.
- When touching proto or Java execution code, run `gradle generateProto`, `gradle shadowJar`, and `gradle test`.

## Assistant Commands And Skills

The `.gemini/commands/` and `.gemini/skills/` trees are retained for Gemini workflows. Speckit templates live in `.specify/`; feature artifacts live in `specs/`.

Useful project commands:

- `/dev.audit`
- `/invest.analyze [ticker_a] [ticker_b]`
- `/speckit.*`

Historical docs such as `docs/bugs.md`, `docs/MONDAY_READINESS_AUDIT.md`, and `docs/geminiplan.md` should be checked against current source before being treated as active findings.
