# Infrastructure

This directory contains the container and deployment wiring for the full bot stack.

## Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Includes backend and frontend compose files |
| `docker-compose.backend.yml` | Redis, PostgreSQL, bot, dashboard/MCP server, Java execution engine, SEC worker |
| `docker-compose.frontend.yml` | Frontend nginx container |
| `docker-compose.local.yml` | Local build override for machines that cannot pull production GHCR images |
| `Dockerfile` | Python runtime image for bot, dashboard API, scripts, and SEC worker |
| `Dockerfile.daemon` | Alternative daemon image |
| `entrypoint.sh` | Default Python bot entrypoint |
| `redeploy.sh` | File watcher/redeploy helper |
| `trading-bot.service` | systemd service template |

## Production Compose

From the repository root:

```bash
docker compose -f infra/docker-compose.yml up -d
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

| Service | Internal port | Host port | Notes |
|---|---:|---:|---|
| `frontend` | `80` | `3000` | nginx static app and API proxy |
| `bot` | `8080` | `8080` | monitor process plus dashboard API |
| `mcp-server` | `8000` | `8000` | FastMCP SSE server when launched via compose command |
| `execution-engine` | `50051` | `50051` | Java gRPC server |
| `redis` | `6379` | `6379` | telemetry, Kalman state, idempotency |
| `postgres` | `5432` | `5433` | ledger/audit database |

## Useful Commands

```bash
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs -f bot
docker compose -f infra/docker-compose.yml logs -f mcp-server
docker compose -f infra/docker-compose.yml logs -f execution-engine
docker compose -f infra/docker-compose.yml down
```

`redeploy.sh --watch` tracks Python, frontend, and Java source changes, including `execution-engine/src/` and `execution-engine/build.gradle.kts`, and rebuilds the affected service.
