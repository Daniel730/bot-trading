#!/usr/bin/env bash
set -euo pipefail
docker cp /tmp/redis_service.py trading-bot-bot-1:/app/src/services/redis_service.py
docker cp /tmp/config.py trading-bot-bot-1:/app/src/config.py
docker cp /tmp/redis_service.py trading-bot-sec-worker-1:/app/src/services/redis_service.py
docker cp /tmp/config.py trading-bot-sec-worker-1:/app/src/config.py
docker cp /tmp/redis_service.py trading-bot-mcp-server-1:/app/src/services/redis_service.py
docker cp /tmp/config.py trading-bot-mcp-server-1:/app/src/config.py
echo "=== config has TTL? ==="
docker exec trading-bot-bot-1 grep -n KALMAN_STATE_TTL /app/src/config.py | head -5
echo "=== restart bot to load modules ==="
docker restart trading-bot-bot-1
sleep 12
docker ps --filter name=trading-bot-bot-1 --format '{{.Names}} {{.Status}}'
echo "=== redis ping after restart ==="
docker exec -i trading-bot-bot-1 python3 - <<'PY'
import asyncio
from src.config import settings
from src.services.redis_service import redis_service, REDIS_KEY_NAMESPACES
print("KALMAN_STATE_TTL_SECONDS", getattr(settings, "KALMAN_STATE_TTL_SECONDS", None))
print("namespaces", "kalman" in REDIS_KEY_NAMESPACES)
async def main():
    c = redis_service._get_instance().client
    print("ping", await c.ping())
    cursor = 0
    with_ttl = no_ttl = 0
    while True:
        cursor, keys = await c.scan(cursor=cursor, match="kalman:*", count=100)
        for key in keys:
            ttl = await c.ttl(key)
            if ttl < 0:
                no_ttl += 1
            else:
                with_ttl += 1
        if cursor == 0:
            break
    print(f"kalman_with_ttl={with_ttl} kalman_no_ttl={no_ttl}")
asyncio.run(main())
PY
echo "=== DONE ==="
