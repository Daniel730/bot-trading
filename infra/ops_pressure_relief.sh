#!/usr/bin/env bash
# Pin discovery bounds + soft-cap neighbor stacks. Avoids volume wipe.
# Recreates only bot if --recreate-bot is passed (sibling-safe default: env pin only).
set -euo pipefail

RECREATE=0
DISABLE_SCOUT=0
for arg in "$@"; do
  case "$arg" in
    --recreate-bot) RECREATE=1 ;;
    --disable-scout) DISABLE_SCOUT=1 ;;
  esac
done

ENV_FILE="${APP_ENV_FILE:-$HOME/.env.trading}"
ROOT="${COMPOSE_ROOT:-$HOME/actions-runner/_work/bot-trading/bot-trading}"
export APP_ENV_FILE="$ENV_FILE"
export BOT_HOST_PORT="${BOT_HOST_PORT:-8082}"
export IMAGE_OWNER="${IMAGE_OWNER:-daniel730}"

echo "=== pressure relief $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
free -h | head -3

# Soft-cap neighbors (no recreate)
SOFT_SCRIPT=""
for candidate in \
  "$ROOT/infra/ops_apply_host_soft_limits.sh" \
  /tmp/ops_apply_host_soft_limits.sh \
  "$HOME/infra-host/ops_apply_host_soft_limits.sh"; do
  if [[ -f "$candidate" ]]; then
    SOFT_SCRIPT="$candidate"
    break
  fi
done
if [[ -n "$SOFT_SCRIPT" ]]; then
  bash "$SOFT_SCRIPT" || true
else
  echo "soft-limits script missing; skip"
fi

python3 - <<'PY' "$ENV_FILE" "$DISABLE_SCOUT"
from pathlib import Path
import sys
env_path = Path(sys.argv[1])
disable_scout = sys.argv[2] == "1"
text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
lines = text.splitlines()
wanted = {
    "PAIR_DISCOVERY_MAX_TICKERS": "8",
    "PAIR_DISCOVERY_AUTO_PROMOTE": "false",
}
if disable_scout:
    wanted["PAIR_DISCOVERY_ENABLED"] = "false"
else:
    wanted["PAIR_DISCOVERY_ENABLED"] = "true"

keys = set(wanted)
out = []
seen = set()
for line in lines:
    raw = line.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        out.append(line)
        continue
    body = raw[7:].strip() if raw.startswith("export ") else raw
    k, _, _ = body.partition("=")
    k = k.strip()
    if k in keys:
        out.append(f"{k}={wanted[k]}")
        seen.add(k)
    else:
        out.append(line)
for k, v in wanted.items():
    if k not in seen:
        out.append(f"{k}={v}")
env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
print("pinned", wanted)
PY

# Show non-secret pins
grep -E '^(PAIR_DISCOVERY_|PAIR_DENYLIST)' "$ENV_FILE" || true

if [[ "$RECREATE" == "1" ]]; then
  echo "--- recreate bot/mcp to pick up env (volumes kept) ---"
  cd "$ROOT"
  docker compose --env-file "$ENV_FILE" -p trading-bot \
    -f infra/docker-compose.backend.yml \
    up -d --no-deps --no-build bot mcp-server
  sleep 8
fi

echo "--- post ---"
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}' | head -25
docker exec trading-bot-bot-1 python3 -c 'from src.config import settings; print(settings.PAIR_DISCOVERY_ENABLED, settings.PAIR_DISCOVERY_MAX_TICKERS, settings.PAIR_DISCOVERY_AUTO_PROMOTE)' 2>/dev/null || echo "bot not ready / old process still running until recreate"
free -h | head -3
echo "PRESSURE_RELIEF_DONE"
