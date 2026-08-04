#!/usr/bin/env bash
# Recreate trading-bot app containers with APP_ENV_FILE set (no volume wipe).
set -euo pipefail
ROOT="${COMPOSE_ROOT:-$HOME/actions-runner/_work/bot-trading/bot-trading}"
export APP_ENV_FILE="${APP_ENV_FILE:-$HOME/.env.trading}"
export BOT_HOST_PORT="${BOT_HOST_PORT:-8082}"
export IMAGE_OWNER="${IMAGE_OWNER:-daniel730}"
cd "$ROOT"
docker compose --env-file "$APP_ENV_FILE" -p trading-bot \
  -f infra/docker-compose.backend.yml \
  up -d --no-deps --no-build bot sec-worker
sleep 10
docker exec trading-bot-bot-1 python3 -c 'from src.config import settings; print("discovery", settings.PAIR_DISCOVERY_ENABLED, settings.PAIR_DISCOVERY_MAX_TICKERS, settings.PAIR_DISCOVERY_AUTO_PROMOTE)'
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}' | head -20
free -h | head -3
echo "BOT_RECREATE_DONE"
