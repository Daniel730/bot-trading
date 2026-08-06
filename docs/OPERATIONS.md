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
- `NEWS_RISK_ENABLED=false` (default). Veto-only news overlay — keep off unless you configure
  `NEWS_RISK_PROVIDER` + `NEWS_RISK_FEED_URLS` (RSS) or `polygon` with a usable Polygon key.
  Missing feed/API does **not** block entries (inactive no-veto).

## Paper Startup Check

Before starting a paper session from the host, run:

```bash
python scripts/paper_startup_check.py .env
```

This repairs only non-secret paper startup keys, validates the env file, and fails closed if Docker, Redis, or PostgreSQL are unreachable.
If it reports already-running app containers, stop them first:

```bash
docker stop infra-bot-1 infra-sec-worker-1 infra-frontend-1
# Optional profile sidecars (only if previously started with --profile optional):
# docker stop infra-execution-engine-1 infra-mcp-server-1
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

Optional FastMCP tool server (loopback by default; `execute_trade` always rejects):

```bash
python src/mcp_server.py
# Override only inside Docker: MCP_HOST=0.0.0.0 MCP_ALLOW_NON_LOOPBACK=true
# Optional tool gate: MCP_TOOL_TOKEN=... (pass auth_token= to each tool)
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

## Host publish hardening (bot-server)

Compose publishes Redis (`6379`), Postgres (`5433`), FastMCP (`8000`), and the Java gRPC engine (`50051`) on **`127.0.0.1` only**. Inter-container traffic still uses the Docker network (`redis` / `postgres` hostnames) and does **not** go through host publishes.

Redis requires `REDIS_PASSWORD` (compose `--requirepass`). Store it only in `/home/daniel/.env.trading` (never commit). Bot/MCP/execution-engine/sec-worker read it via `env_file`; host-side `redis-cli` must use `-a` against `127.0.0.1:6379`.

**Do not rotate `REDIS_PASSWORD` in the env file alone.** Compose bakes `--requirepass` into the Redis container command at create time; changing the env without recreating `trading-bot-redis-1` leaves clients with a new password against the old requirepass and breaks AUTH. Prefer leaving a strong existing password in place. If rotation is required: update `~/.env.trading`, then `docker compose ... up -d --force-recreate --no-deps redis` and recreate dependents so every service picks up the same value. `infra/ops_apply_loopback_binds.sh` only adds/rotates when the password is missing or shorter than 16 characters.

Redis also runs with `--maxmemory 96mb` and `volatile-lru` (under the 128m container `mem_limit`) so TTL-bearing keys can be evicted before Docker OOM-kills Redis.

### Redis key namespaces and TTLs

| Prefix | Purpose | TTL |
|---|---|---|
| `price:{ticker}` | Latest price shadow cache | 10s |
| `kalman:{pair_id}` | Kalman warm-start hash | Sliding `KALMAN_STATE_TTL_SECONDS` (default 14d); quarantine deletes the key |
| `sec:integrity:{ticker}` | SEC fundamental score cache | 24h |
| `cache:*` | Misc caches (e.g. TNX yield) | Caller-supplied |
| `ratelimit:*` | API rate windows | Window length |
| `latency:metrics:raw` | Latency ring buffer | 1h + LTRIM 1000 |
| `execution_attempt:*` / `execution_attempt_lock:*` | Python idempotency | 1h / 60s |
| `execution:inflight:*` | Java order sync | 1h |
| `l2:*` / `l2:snapshot:*` | L2 book snapshots | Writer-supplied |
| `whale:*` | Whale watcher cache (unused while evaluator is dormant; reserved for #91) | `WHALE_WATCHER_CACHE_TTL_SECONDS` |
| `entropy_baseline:*` | Live L2 entropy gate | Persistent (live real-money only) |

Dashboard login sessions are JWT/in-process — **not** stored in Redis. Audit live prefixes with `infra/_redis_lifecycle_probe.sh` (prints counts/TTLs only; never prints the password).

Do not re-bind those ports to `0.0.0.0`/`[::]` — bot-server has LAN and public IPv6. After compose edits, re-apply with `infra/ops_apply_loopback_binds.sh` and confirm with `infra/ops_security_probe.sh`.

Dashboard API (`BOT_HOST_PORT`, usually `8082`) and frontend (`3000`) remain host-reachable for Tailscale/operator access; API routes stay session/token protected (`/ping` is the unauthenticated liveness exception).

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

On **bot-server**, confirm env is valid (prints errors only, never secret values).
The script also fails closed on `MONITOR_ENTRY_ZSCORE < 1.0`, `ORCHESTRATOR_TIMEOUT_SECONDS < 30`,
non-loopback `MCP_HOST` without `MCP_ALLOW_NON_LOOPBACK`, missing/short `REDIS_PASSWORD`, and
compose host publishes that are not `127.0.0.1` for redis/postgres/mcp/gRPC
(`infra/docker-compose.backend.yml` is checked by default; use `--skip-compose` only for env-only):

```bash
python3 scripts/validate_deploy_env.py /home/daniel/.env.trading
```

Confirm these **non-secret** keys in `/home/daniel/.env.trading`:

| Key | Expected on bot-server | Why |
|---|---|---|
| `BOT_HOST_PORT` | `8082` | Avoids SearXNG on `:8080` |
| `ORCHESTRATOR_TIMEOUT_SECONDS` | `60` (or unset → code default 60); validator rejects `< 30` | Agent swarm budget |
| `MONITOR_ENTRY_ZSCORE` | `2.0` (never `0.5`); validator rejects `< 1.0` | Entry threshold; code clamps below 1.0 |
| `IMAGE_OWNER` | `daniel730` | GHCR namespace |
| `POSTGRES_PASSWORD`, `DASHBOARD_TOKEN`, `REDIS_PASSWORD` | non-default; token ≥16 chars; Redis password ≥16 chars | Startup / compose guards (`REDIS_PASSWORD` enables `--requirepass`) |
| `PAIR_DISCOVERY_ENABLED` | `false` (default) | Background scout frozen; curated US universe only |
| `PAIR_DISCOVERY_AUTO_PROMOTE` | `false` (default) | Promote scouts into Active after discover |
| `PAIR_DENYLIST` | includes `BTC-USD_BCH-USD` | Quarantine junk / spread-guard churners |
| `PAIR_DISCOVERY_MAX_TICKERS` | `12` (default); pin `8` on bot-server | Bounds scout RAM/yfinance load |
| `PAIR_DISCOVERY_MAX_ABS_HEDGE` | `25.0` (default) | Equity abs-hedge / Kalman beta ceiling |
| `PAIR_DISCOVERY_MAX_ABS_HEDGE_CRYPTO` | `1000.0` (default) | Crypto abs-hedge ceiling (BTC/ETH ≈ 35 stays tradeable) |
| `PAIR_DISCOVERY_MIN_CORRELATION` | `0.70` (default) | Scout/promote correlation floor |
| `PAIR_DISCOVERY_MAX_PVALUE` | `0.05` (default) | Promote only statistically cointegrated scouts |
| `ELITE_ROTATION_SORTINO_THRESHOLD` | `2.0` (default) | Do not promote weak Sortino scouts |
| `FLAT_ORDER_FRICTION_USD` | `0.0` (default) | Alpaca commission-free; friction uses spreads |
| `SHADOW_FILL_SLIPPAGE_BPS` | `5` (default) | Adverse mid offset on shadow fills |
| `CORP_ACTION_PRICE_JUMP_PCT` | `0.15` (default) | Bench + invalidate Kalman on jump |
| `KELLY_LEDGER_MIN_TRADES` | `20` (default) | Min closed signals before Kelly leaves defaults |
| `NEWS_RISK_ENABLED` | `false` (default) | Opt-in veto-only news overlay (keep off overnight) |
| `TAKE_PROFIT_FORCE_EXIT_ZSCORE` | `0.25` (default) | Exit when mean reversion is done even if fees not cleared |
| `CRYPTO_COINTEGRATION_PVALUE_THRESHOLD` | `0.10` (default) | Tighter than legacy 0.25 crypto ADF gate |
| `PAPER_TRADING` | `true` for paper Alpaca | Do not enable live real-money overnight |

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
execution-engine (optional profile, if Java changed) → sec-worker → bot. Deploy jobs are **serialized**
(`concurrency: deploy-bot-server`) so two compose applies never race. Default runtime stack is
postgres, redis, bot, sec-worker, frontend; `mcp-server` / `execution-engine` stay behind
`--profile optional`.

Images pulled on bot-server:

- `ghcr.io/daniel730/trading-bot-base:latest`
- `ghcr.io/daniel730/trading-frontend:latest`
- `ghcr.io/daniel730/execution-engine:latest` (optional sidecar; only when Java lane deploys)

Env file is bind-mounted read-only; changing env requires **container recreate**, not just restart:

```bash
# On bot-server — after editing /home/daniel/.env.trading
docker compose --env-file /home/daniel/.env.trading -p trading-bot \
  -f ~/actions-runner/_work/bot-trading/bot-trading/infra/docker-compose.backend.yml \
  up -d --no-deps bot sec-worker
# Optional sidecars (only if you want them):
# docker compose ... --profile optional up -d --no-deps mcp-server execution-engine
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
  pull bot sec-worker
docker compose --env-file /home/daniel/.env.trading -p trading-bot \
  -f ~/actions-runner/_work/bot-trading/bot-trading/infra/docker-compose.backend.yml \
  up -d --no-deps bot sec-worker
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
| Env change ignored | Only restarted container | `docker compose up -d` recreate bot/sec-worker |
| Stale code after deploy | Pulled image but old container name | Workflow removes legacy names; run workflow deploy job again |
| Lost 2FA / pairs after deploy | `docker compose down -v` | Restore from backup; volumes are `trading-bot_*` externals |
| Java fix not live | Java path not in redeploy watcher | Re-run workflow with `force_java=true` or touch `execution-engine/` |
| `DEV_MODE=true` in production | Dashboard open, wrong universe | Set `DEV_MODE=false` in env, recreate bot |
| GHCR pull 401 on server | Runner token expired | Re-login on runner host or re-run deploy job (workflow logs in) |
| Container DNS fails (`Temporary failure in name resolution` / yfinance empty / Alpaca unreachable) while host DNS works | Docker embedded DNS forwarding to Tailscale MagicDNS (`100.100.100.100`), which SERVFAILs public names; resolvers are snapshotted at container create | Compose pins `dns: [8.8.8.8, 1.1.1.1]` on bot/sec-worker/optional sidecars. Recreate affected services. Smoke script asserts outbound DNS from the bot container. |

### Deploy log (recent)

| Date | Commits | Workflow | Notes |
|---|---|---|---|
| 2026-08-06 | (compose DNS pin + env defaults) | host recreate (compose file patched on runner workdir; push pending) | Found bot Up 35h but dead trading path: container DNS via MagicDNS SERVFAIL → missing_price on all crypto, Alpaca equity fetch fail. Host DNS OK. Pinned public DNS in `docker-compose.backend.yml`; smoke asserts resolution. Restored overnight soft-admit knobs to defaults (`COINTEGRATION_ROLLING_PASS_RATE=0.7`, `MAX_ACTIVE_PAIRS=12`). |
| 2026-08-04 | `42031a4` (via `8c7df2c`, `9b0bac7`) | [run 30916391994](https://github.com/Daniel730/bot-trading/actions/runs/30916391994) | Phase 4–5 to bot-server. Quality fixes: paper claim fallback; race-safe `begin_intent` ON CONFLICT; brokerage integration test opts into `_pre_submit_gate`. Smoke OK; ~50m soak clean (Restart=0, no CRITICAL/Traceback, Alpaca paper). |
| 2026-07-17 | `7e6f7b3`, `a5c5b63` | [run 29569493017](https://github.com/Daniel730/bot-trading/actions/runs/29569493017) | Profitability fixes: MAB, crypto orchestrator bypass, z-score clamp, take-profit guard, UI label. `force_python` + `force_frontend`. Smoke OK. |

## Host Memory / OOM (bot-server)

bot-server has ~7.4 GiB RAM shared with Minecraft (`-Xmx2G`), AdGuard, Odysseus, Nextcloud, and the trading stack. A week-long outage (exit 137) happened when the bot grew without effective cgroup caps and the host OOM-killer stopped the monitor.

### Guardrails already in compose

| Service | `mem_limit` | `cpus` |
|---|---|---|
| `bot` | 1280m | 1.50 |
| `sec-worker` | 640m | 0.75 |
| `execution-engine` | 512m | 0.75 |
| `mcp-server` | 384m | 0.75 |
| `postgres` | 512m | 1.0 |
| `redis` | 128m | 0.50 |
| `frontend` | 64m | 0.25 |

Verify live caps (non-zero `Mem=` / docker stats LIMIT column):

```bash
bash infra/ops_oom_probe.sh
# or
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}'
```

Scout RAM is bounded by `PAIR_DISCOVERY_MAX_TICKERS` (pin `8` on the shared host; code default `12`). Discovery stays frozen by default (`PAIR_DISCOVERY_ENABLED=false`, `PAIR_DISCOVERY_AUTO_PROMOTE=false`). Keep those false overnight on the shared 7.4 GiB host when the bot is climbing toward its 1280m cgroup cap.

Scan-loop pacing (bot container `cpus: 1.50`): keep `SCAN_PAIR_CONCURRENCY` / `SCAN_EXIT_CONCURRENCY` at `2` (defaults) and `SCAN_COINT_RECHECK_CONCURRENCY=1`. Raise only after RSS/CPU look calm. `SCAN_INTERVAL_SECONDS` is clamped to 5–300 (default 15). Every scannable pair and every open signal still runs each cycle; only parallelism is capped.

Host alert timer (`host-memory-alert.timer`) runs `~/infra-host/memory_alert.sh` every 5 minutes.

### Recover after exit 137 / OOM (never wipe volumes)

```bash
# 1) Baseline + confirm what died
bash infra/ops_oom_probe.sh

# 2) Soft-cap neighbor stacks if they show Mem=0, then start/recreate trading app only
bash infra/ops_oom_recover.sh --apply-soft-limits
# If env pins changed (discovery bounds) and containers must reload .env.trading:
bash infra/ops_recreate_bot_env.sh
# Or full recover recreate path:
bash infra/ops_oom_recover.sh --apply-soft-limits --recreate-bot

# 3) Smoke
bash infra/ops_overnight_check.sh
docker logs trading-bot-bot-1 --since 10m 2>&1 | grep -E 'SCAN \[|MEMORY PRESSURE|OOM|Traceback' | tail -40
```

**Never** `docker compose down -v` on production — that deletes `trading-bot_*` volumes (2FA, pairs, Redis/Postgres).

### Unmanaged broker positions (operator path)

Startup may log `RISK ALERT: Broker has unmanaged position(s) outside the bot ledger`
when Alpaca holds inventory the bot ledger does not track (manual buys, prior runs).
`IGNORE_UNMANAGED_POSITIONS=true` continues scanning without auto-flattening.

**Do not** invent OPEN pair signals for foreign holdings — that would make the bot try to exit them incorrectly.

Acknowledge (paper / broker-paper preferred):

```bash
# List unmanaged vs acknowledged
curl -s -H "X-Dashboard-Session: $SESSION" http://127.0.0.1:8082/api/broker/unmanaged | jq .

# Acknowledge all foreign holdings (no ledger OPEN import)
curl -s -X POST -H "X-Dashboard-Session: $SESSION" -H "Content-Type: application/json" \
  -d '{"acknowledge_all": true, "note": "alpaca_paper_inventory"}' \
  http://127.0.0.1:8082/api/broker/unmanaged/acknowledge

# Or from the host / container CLI
PYTHONPATH=. python scripts/acknowledge_unmanaged_positions.py --list
PYTHONPATH=. python scripts/acknowledge_unmanaged_positions.py --all --note alpaca_paper_inventory
```

Acknowledgements live in Postgres `system_state.unmanaged_positions_acknowledged`
(not ephemeral container FS). Symbol keys are canonicalized to the stripped form
(`BTC-USD` ↔ `BTCUSD`) so restarts and reconciles do not re-alert reviewed inventory.
Clear acknowledgements with `POST /api/broker/unmanaged/clear` if you need the alert again.
Live real-money acknowledge still requires step-up `otp_token` when 2FA is enrolled.
Set `IGNORE_UNMANAGED_POSITIONS=false` only after inventory is closed or acknowledged and you want fail-closed startup.

Neighbor soft caps (AdGuard / Odysseus / NPM / Nextcloud) are applied with `infra/ops_apply_host_soft_limits.sh` via `docker update` (survives until those containers are recreated; re-run after their stack redeploys).

### Troubleshooting

| Symptom | Check |
|---|---|
| App refuses to boot | `POSTGRES_PASSWORD` and `DASHBOARD_TOKEN` must be non-default. |
| Dashboard cannot connect | Backend dashboard API must be listening on `:8080`; check CORS origins. |
| SSE reconnect loop | Confirm `/stream` is reachable and both auth headers are present. |
| WebSocket disconnects | Confirm the initial auth message includes token and session. |
| Java engine exits | Set `DRY_RUN=true`; confirm Redis/Postgres env vars. |
| Equity orders use the wrong broker | Check `BROKERAGE_PROVIDER`; the only active value is `ALPACA`. Unsupported values fail startup. |
| No equity scans | Check market hours and `DEV_MODE`; crypto pairs run 24/7, equity pairs are gated. |
| Crypto pairs only `extreme_kalman_beta` | Confirm `PAIR_DISCOVERY_MAX_ABS_HEDGE_CRYPTO` (≥ observed beta; default 1000). Equity cap stays 25. |
| Wallet sync returns 403 | Live money needs `otp_token` step-up when 2FA is enrolled. Shadow / Alpaca paper (`should_auto_approve_trades`) skips step-up for wallet sync/buys. |
| Unmanaged broker RISK ALERT | Acknowledge via API/CLI (does **not** create OPEN signals). See below. |
| Many pairs rejected | Review `BLOCK_CROSS_CURRENCY_PAIRS`, `BLOCK_LSE_PAIRS_FOR_SHORT_HOLD`, `PAIR_MAX_ROUND_TRIP_COST_PCT`, and `ALLOW_EU_CONTINENTAL_OVERLAP`. |
| Live sell leg rejected before broker | The preflight inventory guard found insufficient available shares. |
| Bot exit 137 / `OOMKilled=true` | Host RAM + compose limits; run `ops_oom_recover.sh`; pin discovery tickers; check Minecraft/`adguardhome` growth. |
| `trading-bot-bot-1` at ~100% of 1.25GiB | Scout/scan pandas pressure; recreate bot; confirm `PAIR_DISCOVERY_MAX_TICKERS` ≤ 8 on bot-server. |

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
