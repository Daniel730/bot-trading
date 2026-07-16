# Operations Guide

This is the day-to-day guide for running the bot locally or through Docker.

## First-Time Setup

```bash
cp .env.template .env
```

Set these before starting anything:

| Variable | Why it matters |
|---|---|
| `POSTGRES_PASSWORD` | Required. The app refuses default/blank database secrets. |
| `DASHBOARD_TOKEN` | Required. Used for dashboard login, session signing, and secret protection. |
| `DASHBOARD_ALLOWED_ORIGINS` | Keep this scoped to the origins you actually use. |
| `PAPER_TRADING=true` | Recommended default while validating the stack. |
| `DRY_RUN=true` | Required for the Java engine today. |

Optional but useful:

- `POLYGON_API_KEY` for market data.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for approvals and login approval notifications.
- `ALPACA_API_KEY`, `ALPACA_API_SECRET`, and `ALPACA_BASE_URL` for the active Alpaca brokerage path.
- `BROKERAGE_PROVIDER=ALPACA`; unsupported values such as `T212` or `WEB3` fail startup.
- Trading 212 and Web3 settings are legacy/disabled in the current runtime.
- `OPENAI_API_KEY` and/or `GEMINI_API_KEY` for model-backed analysis paths.

## Paper Startup Check

Before starting a paper session from the host, run:

```bash
python scripts/paper_startup_check.py .env
```

This repairs only non-secret paper startup keys, validates the env file, and fails closed if Docker, Redis, or PostgreSQL are unreachable.
If it reports already-running app containers, stop them first:

```bash
docker stop infra-bot-1 infra-execution-engine-1 infra-mcp-server-1 infra-sec-worker-1 infra-frontend-1
```

## Local Run

Backend:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip uv
uv pip install -r requirements.lock
python scripts/init_db.py
python src/monitor.py
```

On Windows, use `py -3.11 -m venv .venv` and `.venv\Scripts\Activate.ps1` for the virtual environment steps. Local runs should use `requirements.lock` so they match CI and Docker.

Local tooling note:

- Validated backend commands use the repo WSL/Python 3.11 virtualenv (`.venv/bin/python`).
- Windows `python`/`py` may resolve to Python 3.14; do not use it as proof that the locked backend stack is compatible.
- If `npm` is not installed, frontend gates are not runnable locally; install Node/npm or run the frontend checks in an environment that has them.
- No Gradle wrapper is committed; use an installed `gradle` command for the Java sidecar, or run the Docker build path.

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Java engine:

No Gradle wrapper is committed; use an installed `gradle` command.

```bash
cd execution-engine
gradle shadowJar --no-daemon
DRY_RUN=true gradle run --no-daemon
```

Optional FastMCP tool server:

```bash
python src/mcp_server.py
```

## Docker Run

Production image mode:

```bash
docker compose -f infra/docker-compose.yml up -d
```

Local build mode:

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.local.yml \
  up -d --build --remove-orphans
```

Check status and logs:

```bash
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs -f bot
docker compose -f infra/docker-compose.yml logs -f execution-engine
docker compose -f infra/docker-compose.yml logs -f frontend
```

## Dashboard Login

1. Open `http://localhost:3000` in Docker or the Vite dev URL locally.
2. Enter `DASHBOARD_TOKEN`.
3. If Telegram notifications are configured, approve the login notification.
4. If TOTP is enabled, provide an authenticator or backup code when needed.

The dashboard removes old `token`/`session` query params from the URL. API auth is header-based.

## Operating Modes

| Mode | Settings | Notes |
|---|---|---|
| Paper (shadow) | `PAPER_TRADING=true` | Shadow service simulates entries/exits; approvals auto-accept. |
| Alpaca paper | `PAPER_TRADING=false`, `LIVE_CAPITAL_DANGER=true`, `ALPACA_BASE_URL=https://paper-api.alpaca.markets`, `DEV_MODE=false` | Real orders on Alpaca paper money; approvals auto-accept without Telegram (`should_auto_approve_trades`). |
| Live broker | `PAPER_TRADING=false` + live Alpaca URL (`api.alpaca.markets`) | Real money. Telegram/dashboard approval required; never unattended auto-approve. |
| Broker selection | `BROKERAGE_PROVIDER=ALPACA` | Alpaca is the only active brokerage provider; unsupported values fail startup. |
| Dev | `DEV_MODE=true` | Crypto test universe, 24/7 scan, equity-hour bypass. Do not use for production decisions. |
| Java dry run | `DRY_RUN=true` | Required. The Java engine rejects live-broker mode today. |

## Daily Checks

- Confirm dashboard mode shows the expected `PAPER`, `LIVE`, or `DEV` state.
- Confirm Redis and PostgreSQL are healthy.
- Confirm the scan loop logs `SCAN [A/B]` lines.
- Confirm pair rejections are expected when eligibility filtering is enabled.
- Watch `/api/system/health` or the System Health dashboard page for CPU/memory pressure.
- In paper mode, verify `signal_id` joins across reasoning, journal, and trade ledger.
- In Alpaca paper mode, confirm dashboard shows `ALPACA_PAPER` / `broker_paper_trading=true` (unattended auto-approve is expected).
- In live real-money mode, confirm Telegram/dashboard approval, active broker connectivity, and sell-inventory preflight before enabling execution.

## Telegram And Dashboard Commands

Telegram handlers include:

| Command | Purpose |
|---|---|
| `/exposure` | Sector exposure summary |
| `/invest` | Investment helper entrypoint |
| `/cash` | Account cash and sweep status |
| `/portfolio` | Portfolio view |
| `/why TICKER` | Current thesis/explanation for a ticker |
| `/macro` | Macro/regime summary |

Dashboard terminal handlers include:

| Command | Purpose |
|---|---|
| `/status` | Send current dashboard state |
| `/approve <id>` | Approve a pending dashboard/Telegram correlation id |
| `/set_threshold <amount>` | Update auto-trade approval threshold |
| `/exposure` | Dashboard exposure summary |

## Troubleshooting

| Symptom | Check |
|---|---|
| App refuses to boot | `POSTGRES_PASSWORD` and `DASHBOARD_TOKEN` must be non-default. |
| Dashboard cannot connect | Backend dashboard API must be listening on `:8080`; check CORS origins. |
| SSE reconnect loop | Confirm `/stream` is reachable and both auth headers are present. |
| WebSocket disconnects | Confirm the initial auth message includes token and session. |
| Java engine exits | Set `DRY_RUN=true`; confirm Redis/Postgres env vars. |
| Equity orders use the wrong broker | Check `BROKERAGE_PROVIDER`; the only active value is `ALPACA`. Unsupported values fail startup. |
| No equity scans | Check market hours and `DEV_MODE`; crypto pairs run 24/7, equity pairs are gated. |
| Many pairs rejected | Review `BLOCK_CROSS_CURRENCY_PAIRS`, `BLOCK_LSE_PAIRS_FOR_SHORT_HOLD`, `PAIR_MAX_ROUND_TRIP_COST_PCT`, and `ALLOW_EU_CONTINENTAL_OVERLAP`. |
| Live sell leg rejected before broker | The preflight inventory guard found insufficient available shares. |

## Decision Flight Recorder (incident packs)

Compact decision trails are recorded in-memory at typed skip / veto / execute / anomaly branch points (`DECISION_TRACE_LEVEL=compact|verbose|off`, default `compact`). They join existing journals via `signal_id` — they do **not** duplicate AgentReasoning / TradeJournal rows.

Export a pack for Cursor/Hermes:

```bash
PYTHONPATH=. python scripts/export_incident_pack.py --last-anomaly
PYTHONPATH=. python scripts/export_incident_pack.py --signal-id <uuid>
PYTHONPATH=. python scripts/export_incident_pack.py --scan-id scan-<id>
```

Packs land under `data/incident_packs/<timestamp>_<label>/` with `manifest.json`, `trail.jsonl`, `summary.md`, and `AGENT_HINT.md`.

Note: the ring buffer lives in the running monitor process. The CLI seeds a demo trail when the buffer is empty so pack layout can be validated offline; for a live incident, export from the same process that ran the scan (or restart is not required if you call `decision_recorder.export_pack` in-process).
