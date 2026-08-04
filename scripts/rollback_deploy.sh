#!/usr/bin/env bash
# One-command production rollback for bot-server (Phase-5 ops).
# Target: redeploy previous known-good image tag in < 30s of operator time
# (pull+recreate dominates wall clock; no volume wipe, no manual compose surgery).
#
# Usage on bot-server:
#   bash scripts/rollback_deploy.sh                 # uses PREVIOUS_IMAGE_TAG or IMAGE_TAG-1 file
#   bash scripts/rollback_deploy.sh <git-sha>       # explicit previous tag
#   ROLLBACK_TAG=<sha> bash scripts/rollback_deploy.sh
#
# Never runs `docker compose down -v`.
set -euo pipefail

ENV_FILE="${APP_ENV_FILE:-/home/daniel/.env.trading}"
COMPOSE_ROOT="${BOT_TRADING_ROOT:-$HOME/actions-runner/_work/bot-trading/bot-trading}"
BACKEND_COMPOSE="$COMPOSE_ROOT/infra/docker-compose.backend.yml"
STATE_FILE="${ROLLBACK_STATE_FILE:-/home/daniel/.trading_bot_image_tag}"

fail() { echo "ROLLBACK FAIL: $*" >&2; exit 1; }

[[ -f "$ENV_FILE" ]] || fail "missing env file: $ENV_FILE"
[[ -f "$BACKEND_COMPOSE" ]] || fail "missing compose: $BACKEND_COMPOSE"

TARGET_TAG="${1:-${ROLLBACK_TAG:-}}"
if [[ -z "$TARGET_TAG" && -f "$STATE_FILE" ]]; then
  # File format: current_tag\nprevious_tag
  TARGET_TAG="$(sed -n '2p' "$STATE_FILE" | tr -d '[:space:]')"
fi
[[ -n "$TARGET_TAG" ]] || fail "no rollback tag — pass SHA or set ROLLBACK_TAG / $STATE_FILE"

echo "=== ROLLBACK $(date -u +%Y-%m-%dT%H:%M:%SZ) → IMAGE_TAG=$TARGET_TAG ==="
START=$(date +%s)

# Remember current tag as previous for next rollback.
CURRENT="$(docker inspect trading-bot-bot-1 --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' 2>/dev/null || true)"
if [[ -z "$CURRENT" ]]; then
  CURRENT="$(grep -E '^IMAGE_TAG=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '\"' || true)"
fi
{
  echo "$TARGET_TAG"
  echo "${CURRENT:-unknown}"
} > "$STATE_FILE.tmp"
mv "$STATE_FILE.tmp" "$STATE_FILE"

export IMAGE_TAG="$TARGET_TAG"
docker compose --env-file "$ENV_FILE" -p trading-bot -f "$BACKEND_COMPOSE" pull bot mcp-server sec-worker
docker compose --env-file "$ENV_FILE" -p trading-bot -f "$BACKEND_COMPOSE" up -d --no-deps bot mcp-server sec-worker

END=$(date +%s)
echo "=== ROLLBACK DONE in $((END - START))s ==="
echo "Next: bash scripts/post_deploy_smoke.sh"
unset IMAGE_TAG
