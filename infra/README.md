# Infrastructure

This directory contains the container and deployment wiring for the full bot stack.

## Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Includes backend and frontend compose files |
| `docker-compose.backend.yml` | Redis, PostgreSQL, bot, SEC worker; optional-profile MCP + Java execution engine |
| `docker-compose.frontend.yml` | Frontend nginx container |
| `docker-compose.local.yml` | Local build override for machines that cannot pull production GHCR images |
| `Dockerfile` | Python runtime image for bot, dashboard API, scripts, and SEC worker |
| `Dockerfile.daemon` | Alternative daemon image |
| `entrypoint.sh` | Default Python bot entrypoint |
| `redeploy.sh` | File watcher/redeploy helper |
| `trading-bot.service` | systemd service template |

## Persistent data

Named volumes survive image pulls and container recreates:

| Volume | Mount | Contents |
|---|---|---|
| `trading-bot_redis_data` | redis `/data` | Redis AOF |
| `trading-bot_postgres_data` | postgres data dir | Ledger / audit DB |
| `trading-bot_bot_data` | `/app/data` on bot, mcp-server, sec-worker | Dashboard overrides (`bot_settings.json`, `pairs.json`), SQLite (`trading_bot.db` incl. 2FA), local bot state |

Create them once on a fresh host:

```bash
docker volume create trading-bot_redis_data
docker volume create trading-bot_postgres_data
docker volume create trading-bot_bot_data
```

Never run `docker compose down -v` on production unless you intentionally wipe state.
Secrets and broker URLs also stay in the bind-mounted env file (`APP_ENV_FILE`, e.g. `/home/daniel/.env.trading`).

## Production Compose

From the repository root:

```bash
docker compose -f infra/docker-compose.yml up -d
```

Default stack: `redis`, `postgres`, `bot`, `sec-worker`, `frontend`.

Optional dry-run sidecars (`mcp-server`, `execution-engine`) are behind Compose profile `optional`:

```bash
docker compose -f infra/docker-compose.yml --profile optional up -d
```

The production files pull images from:

- `ghcr.io/${IMAGE_OWNER:-daniel730}/trading-bot-base:${IMAGE_TAG:-latest}`
- `ghcr.io/${IMAGE_OWNER:-daniel730}/execution-engine:${IMAGE_TAG:-latest}`
- `ghcr.io/${IMAGE_OWNER:-daniel730}/trading-frontend:${IMAGE_TAG:-latest}`

## Local Build Compose

Use the local override when you want to build images on the current machine:

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.local.yml \
  up -d --build --remove-orphans
```

## Environment

By default the compose files mount `../.env` into containers. Override with:

```bash
APP_ENV_FILE=/absolute/path/to/.env docker compose -f infra/docker-compose.yml up -d
```

Common image overrides:

```bash
IMAGE_OWNER=my-ghcr-owner IMAGE_TAG=my-tag docker compose -f infra/docker-compose.yml up -d
```

## Services And Ports

| Service | Internal port | Host publish | Restart | Notes |
|---|---:|---|---|---|
| `frontend` | `80` | `3000` | `unless-stopped` | nginx static app and API proxy (LAN/Tailscale OK) |
| `bot` | `8080` | `${BOT_HOST_PORT:-8080}` (8082 on bot-server) | `unless-stopped` | monitor + dashboard API (#137) |
| `sec-worker` | — | — | `unless-stopped` | SEC scoring daemon |
| `mcp-server` | `8000` | `127.0.0.1:8000` | `no` | Optional (`--profile optional`); FastMCP; host publish loopback only |
| `execution-engine` | `50051` | `127.0.0.1:50051` | `unless-stopped` | Optional (`--profile optional`); Java gRPC dry-run sidecar — loopback only |
| `redis` | `6379` | `127.0.0.1:6379` | `always` | requirepass via `REDIS_PASSWORD`; clients use host `redis` on the compose network |
| `postgres` | `5432` | `127.0.0.1:5433` | `always` | ledger/audit DB — loopback only |

Containers talk over the compose network with service DNS (`REDIS_HOST=redis`, `POSTGRES_HOST=postgres`). Host port publishes are for operator tooling on localhost only. Re-apply binds + Redis auth with `ops_apply_loopback_binds.sh`; probe with `ops_security_probe.sh`.

`bot` uses `restart: unless-stopped` so the monitor returns after host reboot / dockerd restart. Explicit `docker stop` still sticks until you start it again. See `docs/OPERATIONS.md` (Production Deploy) for the `docker update --restart` hotfix path.

## Useful Commands

Useful commands note optional profile for MCP/Java:

```bash
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs -f bot
docker compose -f infra/docker-compose.yml --profile optional logs -f mcp-server
docker compose -f infra/docker-compose.yml --profile optional logs -f execution-engine
docker compose -f infra/docker-compose.yml down
```

`redeploy.sh --watch` tracks Python, frontend, and Java source changes, including `execution-engine/src/` and `execution-engine/build.gradle.kts`, and rebuilds the affected service.

## Resource limits

Compose services declare `mem_limit` / `cpus` so the trading stack cannot unbounded-grow on a shared host (for example bot-server alongside other workloads). Tune in `infra/docker-compose.backend.yml` and `infra/docker-compose.frontend.yml` if the host profile changes.

OOM probe / recover helpers on the shared host:

- `infra/ops_oom_probe.sh` — host + container memory baseline
- `infra/ops_oom_recover.sh` — start/recreate trading app without wiping volumes
- `infra/ops_apply_host_soft_limits.sh` — soft-cap AdGuard/Odysseus/NPM/Nextcloud via `docker update`
- `infra/ops_recreate_bot_env.sh` — recreate bot/mcp after `.env.trading` discovery pins

Host-only ops scripts (HDD, Pi edge, Minecraft limits) may live under `infra/host/` on the operator machine; they are not required to run the bot.

## Production deploy (bot-server)

Full checklist, smoke tests, rollback, and common bugs: [`docs/OPERATIONS.md`](../docs/OPERATIONS.md#production-deploy-bot-server).

Quick trigger from dev machine after `git push origin master`:

```bash
gh workflow run "Deploy to bot-server (Mini PC)" --ref master
```

Post-deploy smoke on bot-server: `bash scripts/post_deploy_smoke.sh`

Extended soak/health probe (binds, RSS, SEC keys, frontend markers): `bash infra/ops_postdeploy_health.sh`
