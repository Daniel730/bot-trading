# bot-trading Development Guidelines

Last refreshed: 2026-08-10

This file orients Gemini-style assistant sessions. For the full current docs, start at `README.md` and `docs/README.md`. Required agent process: `docs/AGENT_WORKFLOW.md`. Copilot custom agents: `.github/agents/` (see `.github/copilot-instructions.md`).

## Active Technologies

- Python 3.11
- FastAPI, FastMCP, SSE, WebSocket telemetry (`telemetry_service` is an internal queue/broadcast stub — not vendor APM)
- pandas, numpy, scipy, statsmodels, yfinance, Polygon client
- Pydantic v2 settings
- Redis, PostgreSQL, SQLite
- gRPC Python stubs and Java gRPC dry-run service
- Java 21 with Gradle (no wrapper committed)
- React 19, Vite 8, TypeScript, Vitest, ESLint 9 (Biome not yet; see #123)
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

- `PAPER_TRADING=true` is the safe default and routes fills through the shadow service (SHADOW lane).
- `PAPER_TRADING=false` + Alpaca paper API (`paper-api.alpaca.markets`) is BROKER_PAPER: real paper orders, auto-approve via `should_auto_approve_trades`. Requires `LIVE_CAPITAL_DANGER=true`.
- Real-money live uses `api.alpaca.markets` and always needs human approval (Telegram/dashboard).
- `BROKERAGE_PROVIDER` must be `ALPACA`; `T212` and `WEB3` fail startup (legacy/disabled).
- `DEV_MODE=true` is for crypto-only 24/7 development behavior and should not be used for production decisions.
- `DRY_RUN=true` is required for the Java engine because live Java brokerage is intentionally blocked.
- Dashboard API runs on port `8080` (Compose may publish as `BOT_HOST_PORT`, e.g. `8082` on bot-server); optional FastMCP runs on port `8000`.
- Dashboard login is fail-closed (Telegram approval or TOTP/backup when 2FA is enabled — no token-only session). Sensitive config writes require 2FA after setup.
- Pair universe and settings can be overridden at runtime through `data/pairs.json` and `data/bot_settings.json`.
- Compose `bot` / `sec-worker` / `frontend` / `execution-engine` use `restart: unless-stopped` (Redis/Postgres `always`; optional `mcp-server` is `restart: "no"`).

## Commands

Prefer the locked deps used by CI/Docker:

```bash
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
uv pip install -r requirements.lock
PYTHONPATH=. python scripts/init_db.py
PYTHONPATH=. python -m src.monitor
PYTHONPATH=. python src/mcp_server.py
PYTHONPATH=. pytest tests/ -v --asyncio-mode=auto
```

```bash
cd frontend
npm install --legacy-peer-deps
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
- Keep venue routing centralized in `BrokerageService.get_venue()`. Active runtime supports `BROKERAGE_PROVIDER=ALPACA` only; T212/Web3 settings remain in code/config but fail startup.
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
