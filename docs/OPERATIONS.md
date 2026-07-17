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

## Pytest In Docker

`tests/unit/test_backend_compose_secrets.py` reads compose files from the repo `infra/` directory. If you run the full pytest suite inside a container whose workdir is only `/app` source without `infra/`, those tests fail with a false negative.

Mount the compose tree (or copy it into the image) before running Dockerized pytest, for example:

```bash
docker run --rm -v "$PWD:/app" -v "$PWD/infra:/app/infra" -w /app <test-image> \
  pytest tests/unit/test_backend_compose_secrets.py -q --asyncio-mode=auto
```

Local pytest from the repo root does not need this mount.

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

## Production Deploy (bot-server)

Production runs on **bot-server** (`daniel@bot-server`) via GitHub Actions and GHCR images.
The self-hosted runner applies compose with project name `trading-bot` and env file
`/home/daniel/.env.trading`. Dashboard/API is on **http://bot-server:8082** (`BOT_HOST_PORT=8082`).

Workflow definition: [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)

### Pre-flight checklist

Run from your dev machine **before** pushing:

```bash
# 1. Tests green on the commits you are about to deploy
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/test_monitor.py \
  tests/unit/test_orchestrator_fundamentals.py tests/unit/test_reflection_mab.py \
  tests/unit/test_config_env_parsing.py -q --asyncio-mode=auto

# 2. No secrets in the diff
git diff --stat origin/master..HEAD
```

On **bot-server**, confirm env is valid (prints errors only, never secret values):

```bash
python3 scripts/validate_deploy_env.py /home/daniel/.env.trading
```

Confirm these **non-secret** keys in `/home/daniel/.env.trading`:

| Key | Expected on bot-server | Why |
|---|---|---|
| `BOT_HOST_PORT` | `8082` | Avoids SearXNG on `:8080` |
| `ORCHESTRATOR_TIMEOUT_SECONDS` | `60` (or unset → code default 60) | Agent swarm budget |
| `MONITOR_ENTRY_ZSCORE` | `2.0` (never `0.5`) | Entry threshold; code clamps below 1.0 |
| `IMAGE_OWNER` | `daniel730` | GHCR namespace |
| `POSTGRES_PASSWORD`, `DASHBOARD_TOKEN` | non-default, ≥16 chars for token | Startup guards |

**Do not** set `MONITOR_ENTRY_ZSCORE=0.5` in env or `data/bot_settings.json` — the runtime
clamps to 1.0 and logs a warning, but the intent is wrong and hides misconfiguration.

Named volumes must exist (survive image pulls; hold 2FA, pairs, SQLite):

```bash
docker volume create trading-bot_redis_data
docker volume create trading-bot_postgres_data
docker volume create trading-bot_bot_data
```

First-time host prep: `infra/prepare_bot_server_env.sh` (sets `BOT_HOST_PORT=8082`, creates volumes).

### Deploy steps (standard path)

1. **Push** commits to `origin/master` (CI builds on GitHub-hosted runners, deploys on bot-server runner).

```bash
git push origin master
```

2. **Trigger** the workflow (from dev machine with `gh` CLI):

```bash
# Normal: only rebuild/deploy lanes that changed since last commit
gh workflow run "Deploy to bot-server (Mini PC)" --ref master

# When you touched Python + frontend (or want to be sure):
gh workflow run "Deploy to bot-server (Mini PC)" --ref master \
  -f force_python=true -f force_frontend=true

# Full stack (release-like):
gh workflow run "Deploy to bot-server (Mini PC)" --ref master -f force_all=true
```

3. **Watch** the run:

```bash
gh run watch   # pick the latest "Deploy to bot-server" run
gh run view --log-failed   # if something breaks
```

Pipeline order: quality gates → build & push GHCR (`:latest` + commit SHA) → deploy frontend →
execution-engine (if Java changed) → sec-worker → bot + mcp-server. Deploy jobs are **serialized**
(`concurrency: deploy-bot-server`) so two compose applies never race.

Images pulled on bot-server:

- `ghcr.io/daniel730/trading-bot-base:latest`
- `ghcr.io/daniel730/trading-frontend:latest`
- `ghcr.io/daniel730/execution-engine:latest` (or pinned tag if unchanged)

Env file is bind-mounted read-only; changing env requires **container recreate**, not just restart:

```bash
# On bot-server — after editing /home/daniel/.env.trading
docker compose --env-file /home/daniel/.env.trading -p trading-bot \
  -f ~/actions-runner/_work/bot-trading/bot-trading/infra/docker-compose.backend.yml \
  up -d --no-deps bot mcp-server sec-worker
```

### Post-deploy smoke tests

On bot-server (copy script or run from repo checkout):

```bash
bash scripts/post_deploy_smoke.sh
```

From a workstation over SSH:

```bash
ssh daniel@bot-server 'bash -s' < scripts/post_deploy_smoke.sh
```

Manual spot checks:

```bash
# Containers up, bot on :8082
docker ps --filter name=trading-bot

# Scan loop active (expect SCAN [pair] lines within ~15 min of boot)
docker logs trading-bot-bot-1 --since 15m 2>&1 | grep 'SCAN \[' | tail -5

# Runtime settings inside the running image
docker exec trading-bot-bot-1 python3 -c \
  "from src.config import settings; print(settings.ORCHESTRATOR_TIMEOUT_SECONDS, settings.MONITOR_ENTRY_ZSCORE)"
```

Health endpoint returns **401** without dashboard auth — that is correct (fail-closed).

### Rollback

If a deploy misbehaves, re-deploy the previous image tag without wiping volumes:

```bash
# On bot-server — pin to a known-good SHA tag from GHCR
export IMAGE_TAG=<previous-commit-sha>
docker compose --env-file /home/daniel/.env.trading -p trading-bot \
  -f ~/actions-runner/_work/bot-trading/bot-trading/infra/docker-compose.backend.yml \
  pull bot mcp-server sec-worker
docker compose --env-file /home/daniel/.env.trading -p trading-bot \
  -f ~/actions-runner/_work/bot-trading/bot-trading/infra/docker-compose.backend.yml \
  up -d --no-deps bot mcp-server sec-worker
unset IMAGE_TAG
```

Or re-run the GitHub workflow on the previous `master` commit via `workflow_dispatch` after
`git revert` and push. **Never** `docker compose down -v` on production unless intentionally
wiping Redis, Postgres, and dashboard 2FA state.

### Common deploy bugs (and fixes)

| Symptom | Likely cause | Fix |
|---|---|---|
| Bot crash-loops on boot | Default `POSTGRES_PASSWORD` / `DASHBOARD_TOKEN` | Set real secrets; run `validate_deploy_env.py` |
| Bot on wrong port / dashboard 502 | `BOT_HOST_PORT` not 8082 | `infra/prepare_bot_server_env.sh` or set `BOT_HOST_PORT=8082`, recreate bot |
| Trades never fire, z always low | `MONITOR_ENTRY_ZSCORE=0.5` in env or `bot_settings.json` | Remove override; use `2.0`; check clamp warning in logs |
| Orchestrator timeouts on crypto | Old image without crypto macro bypass | Redeploy Python image (`force_python=true`) |
| Env change ignored | Only restarted container | `docker compose up -d` recreate bot/mcp-server |
| Stale code after deploy | Pulled image but old container name | Workflow removes legacy names; run workflow deploy job again |
| Lost 2FA / pairs after deploy | `docker compose down -v` | Restore from backup; volumes are `trading-bot_*` externals |
| Java fix not live | Java path not in redeploy watcher | Re-run workflow with `force_java=true` or touch `execution-engine/` |
| `DEV_MODE=true` in production | Dashboard open, wrong universe | Set `DEV_MODE=false` in env, recreate bot |
| GHCR pull 401 on server | Runner token expired | Re-login on runner host or re-run deploy job (workflow logs in) |

### Deploy log (recent)

| Date | Commits | Workflow | Notes |
|---|---|---|---|
| 2026-07-17 | `7e6f7b3`, `a5c5b63` | [run 29569493017](https://github.com/Daniel730/bot-trading/actions/runs/29569493017) | Profitability fixes: MAB, crypto orchestrator bypass, z-score clamp, take-profit guard, UI label. `force_python` + `force_frontend`. Smoke OK. |

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
