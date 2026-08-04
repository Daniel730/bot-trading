#!/usr/bin/env bash
# Minimal paper-safe Redis TTL hotpatch (no password rotate, no discovery).
set -euo pipefail
echo "=== patch config if needed ==="
docker exec -i trading-bot-bot-1 python3 - <<'PY'
from pathlib import Path
p = Path("/app/src/config.py")
t = p.read_text()
if "KALMAN_STATE_TTL_SECONDS" in t:
    print("config_already_has_kalman_ttl")
else:
    old = 'REDIS_APPENDONLY: bool = Field(default=True, validation_alias="REDIS_APPENDONLY")'
    new = old + "\n    KALMAN_STATE_TTL_SECONDS: int = Field(\n        default=14 * 24 * 3600,\n        validation_alias=\"KALMAN_STATE_TTL_SECONDS\",\n        ge=3600,\n    )"
    if old not in t:
        raise SystemExit("config_anchor_missing")
    p.write_text(t.replace(old, new, 1))
    print("config_patched")
PY
if [ -f /tmp/redis_service.py ]; then
  docker cp /tmp/redis_service.py trading-bot-bot-1:/app/src/services/redis_service.py
  echo "redis_service_copied"
else
  echo "redis_service_missing_at_/tmp" >&2
  exit 1
fi
echo "=== verify files ==="
docker exec trading-bot-bot-1 grep -n KALMAN_STATE_TTL /app/src/config.py | head -5
docker exec trading-bot-bot-1 grep -n "expire(key, ttl)\|REDIS_KEY_NAMESPACES" /app/src/services/redis_service.py | head -5
echo "=== restart bot ==="
docker restart trading-bot-bot-1
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 3
  st=$(docker inspect -f '{{.State.Status}}' trading-bot-bot-1 2>/dev/null || echo missing)
  echo "status_$i=$st"
  if [ "$st" = "running" ]; then
    break
  fi
done
sleep 5
docker exec -i trading-bot-bot-1 python3 - <<'PY'
import asyncio
from src.config import settings
from src.services.redis_service import redis_service, REDIS_KEY_NAMESPACES
print("ttl_setting", getattr(settings, "KALMAN_STATE_TTL_SECONDS", None))
print("has_namespaces", "kalman" in REDIS_KEY_NAMESPACES)
async def main():
    c = redis_service._get_instance().client
    print("ping", await c.ping())
    with_ttl = no_ttl = 0
    cursor = 0
    while True:
        cursor, keys = await c.scan(cursor=cursor, match="kalman:*", count=100)
        for key in keys:
            if await c.ttl(key) < 0:
                no_ttl += 1
            else:
                with_ttl += 1
        if cursor == 0:
            break
    print(f"kalman_with_ttl={with_ttl} kalman_no_ttl={no_ttl}")
asyncio.run(main())
PY
echo "=== DONE ==="
