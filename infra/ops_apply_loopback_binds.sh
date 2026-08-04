#!/usr/bin/env bash
# Persist loopback-only host publishes for redis/postgres/mcp/execution-engine
# and ensure Redis requirepass is enabled via REDIS_PASSWORD in ~/.env.trading.
# Does not wipe volumes. Safe for overnight security remediation.
set -euo pipefail

ENV_FILE="${ENV_FILE:-/home/daniel/.env.trading}"
BOT_HOST_PORT="${BOT_HOST_PORT:-8082}"

resolve_compose_dir() {
  if [ -n "${COMPOSE_DIR:-}" ] && [ -f "${COMPOSE_DIR}/docker-compose.backend.yml" ]; then
    printf '%s\n' "$COMPOSE_DIR"
    return 0
  fi
  local candidates=(
    "/home/daniel/actions-runner/_work/bot-trading/bot-trading/infra"
    "/home/daniel/bot-trading/infra"
    "$(cd "$(dirname "$0")" && pwd)"
  )
  local c
  for c in "${candidates[@]}"; do
    if [ -f "${c}/docker-compose.backend.yml" ]; then
      printf '%s\n' "$c"
      return 0
    fi
  done
  return 1
}

COMPOSE_DIR="$(resolve_compose_dir)" || {
  echo "missing compose dir (set COMPOSE_DIR)" >&2
  exit 1
}
BACKEND="$COMPOSE_DIR/docker-compose.backend.yml"
FRONTEND="$COMPOSE_DIR/docker-compose.frontend.yml"

if [ ! -f "$ENV_FILE" ]; then
  echo "missing env file: $ENV_FILE" >&2
  exit 1
fi

# Fail closed if compose lost loopback publishes (e.g. bad merge / old checkout).
fail_if_public_bind() {
  local svc="$1"
  local port="$2"
  # Extract the ports block for the service and require 127.0.0.1:<port>
  if ! awk -v svc="$svc" -v port="$port" '
    $0 ~ "^  " svc ":" {in_svc=1; next}
    in_svc && $0 ~ /^  [a-z]/ {exit}
    in_svc && $0 ~ /^    ports:/ {in_ports=1; next}
    in_ports && $0 ~ /^    [a-z]/ {in_ports=0}
    in_ports {
      if ($0 ~ "127\\.0\\.0\\.1:" port ":" ) found=1
      if ($0 ~ "0\\.0\\.0\\.0:" port ":" ) bad=1
      if ($0 ~ "\"[0-9]+:" port ) bad=1
      if ($0 ~ "- \"?" port ":" ) bad=1
    }
    END { exit(found && !bad ? 0 : 1) }
  ' "$BACKEND"; then
    echo "REFUSE: $svc must publish 127.0.0.1:${port} only in $BACKEND" >&2
    grep -nE "ports:|${port}|127\\.0\\.0\\.1|0\\.0\\.0\\.0" "$BACKEND" | head -40 >&2 || true
    exit 1
  fi
}

fail_if_public_bind redis 6379
fail_if_public_bind postgres 5433
fail_if_public_bind mcp-server 8000
fail_if_public_bind execution-engine 50051

if ! grep -q 'requirepass' "$BACKEND"; then
  echo "REFUSE: redis service missing requirepass wiring in $BACKEND" >&2
  exit 1
fi

echo "=== port publish lines ==="
grep -nE 'ports:|6379|5433|8000|50051|requirepass|REDIS_PASSWORD' "$BACKEND" | head -50

# Ensure REDIS_PASSWORD exists and is strong enough (never print the value).
ensure_redis_password() {
  python3 - "$ENV_FILE" <<'PY'
import secrets
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
lines = text.splitlines()
idx = None
value = ""
for i, raw in enumerate(lines):
    if raw.startswith("REDIS_PASSWORD="):
        idx = i
        value = raw.split("=", 1)[1].strip().strip("'").strip('"')
        break

changed = False
if idx is None:
    lines.append(f"REDIS_PASSWORD={secrets.token_hex(32)}")
    changed = True
    action = "ADDED_REDIS_PASSWORD"
elif len(value) < 16:
    lines[idx] = f"REDIS_PASSWORD={secrets.token_hex(32)}"
    changed = True
    action = "ROTATED_WEAK_REDIS_PASSWORD"
else:
    action = "REDIS_PASSWORD_OK"

if changed:
    backup = path.with_suffix(path.suffix + ".bak.redis")
    backup.write_text(text, encoding="utf-8")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
    print(action)
    print(f"backup={backup}")
else:
    print(action)
PY
}

ensure_redis_password

export APP_ENV_FILE="$ENV_FILE"
export BOT_HOST_PORT

cd "$COMPOSE_DIR/.."

# Recreate infra publishes + Redis auth first, then consumers so they pick up
# REDIS_PASSWORD from env_file (same docker network; host binds stay loopback).
COMPOSE=(docker compose --env-file "$ENV_FILE" -p trading-bot -f "$BACKEND")
if [ -f "$FRONTEND" ]; then
  COMPOSE+=(-f "$FRONTEND")
fi

"${COMPOSE[@]}" up -d --no-deps redis postgres mcp-server execution-engine
"${COMPOSE[@]}" up -d --no-deps bot sec-worker 2>/dev/null || \
  "${COMPOSE[@]}" up -d --no-deps bot || true

echo "=== listening after apply ==="
ss -tuln | awk 'NR==1 || /:(6379|5433|8000|50051|8082|3000) /'

echo "=== public bind check (expect none on hardened ports) ==="
# Only inspect Local Address (field 5). Peer Address is often 0.0.0.0:* on LISTEN.
if ss -tuln | awk 'NR > 1 && /:(6379|5433|8000|50051) / { print $5 }' | grep -vE '^127\.0\.0\.1:'; then
  echo "FAIL: hardened ports still publicly bound" >&2
  exit 1
fi
echo "public_bind_ok=yes"

echo "=== redis requirepass set? ==="
# Auth with env password without printing it.
if docker exec -e REDIS_PASSWORD_FILE= trading-bot-redis-1 sh -c \
  'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning CONFIG GET requirepass' \
  2>/dev/null | awk 'NR==2 {exit length($0)==0}'; then
  echo "redis_requirepass_set=yes"
else
  # Fallback: unauthenticated CONFIG GET should fail with NOAUTH when set.
  if docker exec trading-bot-redis-1 redis-cli PING 2>&1 | grep -qi NOAUTH; then
    echo "redis_requirepass_set=yes"
  else
    echo "redis_requirepass_set=no" >&2
    exit 1
  fi
fi

echo "=== bot redis ping (service network) ==="
docker exec trading-bot-bot-1 python - <<'PY' || true
import asyncio
from src.services.redis_service import redis_service

async def main():
    pong = await redis_service.client.ping()
    print(f"bot_redis_ping={pong}")

asyncio.run(main())
PY
