#!/usr/bin/env bash
# Hot-patch SEC lane Python into running bot + sec-worker (paper-safe). No volume wipe.
set -euo pipefail
ROOT="${1:-.}"
BOT="${BOT_CONTAINER:-trading-bot-bot-1}"
SEC="${SEC_CONTAINER:-trading-bot-sec-worker-1}"

echo "=== SEC HOTPATCH $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
for f in \
  src/daemons/sec_fundamental_worker.py \
  src/services/sec_service.py \
  src/agents/orchestrator.py \
  src/config.py
do
  echo "cp $f"
  docker cp "$ROOT/$f" "$BOT:/app/$f"
  docker cp "$ROOT/$f" "$SEC:/app/$f"
done

docker update --restart unless-stopped "$SEC" >/dev/null
echo "restart_policy=$(docker inspect "$SEC" --format '{{.HostConfig.RestartPolicy.Name}}')"

echo "restarting $SEC $BOT"
docker restart "$SEC" "$BOT" >/dev/null
sleep 5
docker inspect "$SEC" --format 'sec Status={{.State.Status}} Started={{.State.StartedAt}}'
docker inspect "$BOT" --format 'bot Status={{.State.Status}} Started={{.State.StartedAt}}'
docker logs "$SEC" --tail 15 2>&1 | tail -15
echo "HOTPATCH_DONE"
