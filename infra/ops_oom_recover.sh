#!/usr/bin/env bash
# OOM recovery for trading-bot on bot-server. Never wipes volumes.
# Usage: bash infra/ops_oom_recover.sh [--apply-soft-limits] [--recreate-bot]
set -euo pipefail

APPLY_SOFT=0
RECREATE_BOT=0
for arg in "$@"; do
  case "$arg" in
    --apply-soft-limits) APPLY_SOFT=1 ;;
    --recreate-bot) RECREATE_BOT=1 ;;
    -h|--help)
      echo "Usage: $0 [--apply-soft-limits] [--recreate-bot]"
      exit 0
      ;;
  esac
done

ROOT="${COMPOSE_ROOT:-$HOME/actions-runner/_work/bot-trading/bot-trading}"
ENV_FILE="${APP_ENV_FILE:-$HOME/.env.trading}"
export APP_ENV_FILE="$ENV_FILE"
export BOT_HOST_PORT="${BOT_HOST_PORT:-8082}"
export IMAGE_OWNER="${IMAGE_OWNER:-daniel730}"

echo "=== OOM RECOVER $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "host=$(hostname)"
free -h | head -3

echo "--- recent oom markers ---"
journalctl -k --since "48 hours ago" --no-pager 2>/dev/null \
  | grep -iE "oom|Out of memory|Killed process" | tail -20 || true
dmesg -T 2>/dev/null | grep -iE "oom|Out of memory|Killed process" | tail -10 || true

echo "--- trading-bot state ---"
docker ps -a --filter name=trading-bot --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
for c in trading-bot-bot-1 trading-bot-mcp-server-1 trading-bot-sec-worker-1 \
         trading-bot-execution-engine-1 trading-bot-redis-1 trading-bot-postgres-1; do
  docker inspect "$c" --format \
    '{{.Name}} status={{.State.Status}} oom={{.State.OOMKilled}} exit={{.State.ExitCode}} rc={{.RestartCount}} mem={{.HostConfig.Memory}}' \
    2>/dev/null || echo "MISSING $c"
done

echo "--- ensure compose limits present on disk ---"
if ! grep -q "mem_limit:" "$ROOT/infra/docker-compose.backend.yml" 2>/dev/null; then
  echo "FATAL: backend compose missing mem_limit at $ROOT" >&2
  exit 2
fi
grep -n "mem_limit\|cpus:" "$ROOT/infra/docker-compose.backend.yml" | head -20

# Re-assert execution-engine live limit (historically drifted).
if docker inspect trading-bot-execution-engine-1 >/dev/null 2>&1; then
  docker update --memory=512m --memory-swap=512m --cpus=0.75 trading-bot-execution-engine-1 >/dev/null || true
fi

if [[ "$APPLY_SOFT" == "1" ]]; then
  if [[ -x "$ROOT/infra/ops_apply_host_soft_limits.sh" ]]; then
    bash "$ROOT/infra/ops_apply_host_soft_limits.sh"
  elif [[ -f "$ROOT/infra/ops_apply_host_soft_limits.sh" ]]; then
    bash "$ROOT/infra/ops_apply_host_soft_limits.sh"
  else
    echo "soft-limits script missing; skip"
  fi
fi

if [[ "$RECREATE_BOT" == "1" ]]; then
  echo "--- recreate bot/mcp/sec without touching volumes ---"
  cd "$ROOT"
  docker compose --env-file "$ENV_FILE" -p trading-bot \
    -f infra/docker-compose.backend.yml \
    up -d --no-deps --no-build bot mcp-server sec-worker
else
  # Prefer start over recreate when sibling may be deploying.
  echo "--- start stopped trading-bot containers (no recreate) ---"
  for c in trading-bot-redis-1 trading-bot-postgres-1 trading-bot-execution-engine-1 \
           trading-bot-mcp-server-1 trading-bot-sec-worker-1 trading-bot-bot-1 \
           trading-bot-frontend-1; do
    st=$(docker inspect "$c" --format '{{.State.Status}}' 2>/dev/null || echo missing)
    if [[ "$st" == "exited" || "$st" == "created" ]]; then
      echo "starting $c (was $st)"
      docker start "$c" || true
    else
      echo "ok $c status=$st"
    fi
  done
fi

echo "--- post ---"
free -h | head -3
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}' | head -25
echo "OOM_RECOVER_DONE"
echo "Tip: bash infra/ops_oom_probe.sh for full baseline; never docker compose down -v"
