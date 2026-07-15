#!/usr/bin/env bash
# One-shot: create bot_data volume, seed from live container if possible, recreate python services.
set -euo pipefail

ENV_FILE="${APP_ENV_FILE:-/home/daniel/.env.trading}"
ROOT="${BOT_TRADING_ROOT:-/home/daniel/actions-runner/_work/bot-trading/bot-trading}"
COMPOSE="$ROOT/infra/docker-compose.backend.yml"

docker volume create trading-bot_redis_data >/dev/null
docker volume create trading-bot_postgres_data >/dev/null
docker volume create trading-bot_bot_data >/dev/null

# Seed current container /app/data into the named volume (best-effort).
if docker ps -a --format '{{.Names}}' | grep -qx trading-bot-bot-1; then
  docker run --rm \
    --volumes-from trading-bot-bot-1 \
    -v trading-bot_bot_data:/persist \
    alpine:3.20 \
    sh -c 'mkdir -p /persist && if [ -d /app/data ]; then cp -a /app/data/. /persist/ 2>/dev/null || true; fi; ls -la /persist'
  echo "SEEDED_FROM_CONTAINER"
else
  echo "NO_BOT_CONTAINER_TO_SEED"
fi

# Seed mode flags from env into bot_settings.json on the volume (no secrets).
docker run --rm -v trading-bot_bot_data:/persist -v "$ENV_FILE:/env.trading:ro" alpine:3.20 \
  sh -c 'apk add --no-cache python3 >/dev/null && python3 - <<"PY"
from pathlib import Path
import json
env = {}
for raw in Path("/env.trading").read_text(encoding="utf-8", errors="replace").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k.strip()] = v.strip().strip("\"'")
path = Path("/persist/bot_settings.json")
existing = {}
if path.exists():
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        existing = {}
# Only set mode flags if missing; never wipe existing operator overrides/secrets.
for key, cast in (
    ("PAPER_TRADING", lambda x: str(x).lower() == "true"),
    ("LIVE_CAPITAL_DANGER", lambda x: str(x).lower() == "true"),
    ("DEV_MODE", lambda x: str(x).lower() == "true"),
):
    if key not in existing and key in env:
        existing[key] = cast(env[key])
path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
print("bot_settings_keys=", sorted(existing))
PY'

cd "$ROOT"
export APP_ENV_FILE="$ENV_FILE"
export DEPLOY_ENV_FILE="$ENV_FILE"
export IMAGE_OWNER="${IMAGE_OWNER:-daniel730}"
export IMAGE_TAG="${IMAGE_TAG:-latest}"

docker compose --env-file "$DEPLOY_ENV_FILE" -p trading-bot -f "$COMPOSE" \
  up -d --force-recreate --no-deps bot mcp-server sec-worker

echo "RECREATE_OK"
docker ps --filter name=trading-bot --format 'table {{.Names}}\t{{.Status}}'
docker inspect trading-bot-bot-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
