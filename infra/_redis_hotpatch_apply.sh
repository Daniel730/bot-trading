#!/usr/bin/env bash
set -euo pipefail
docker cp /tmp/redis_service.py trading-bot-bot-1:/app/src/services/redis_service.py
docker cp /tmp/redis_service.py trading-bot-sec-worker-1:/app/src/services/redis_service.py
docker cp /tmp/redis_service.py trading-bot-mcp-server-1:/app/src/services/redis_service.py
echo "=== grep TTL wiring ==="
docker exec trading-bot-bot-1 grep -n "expire(key, ttl)\|REDIS_KEY_NAMESPACES\|delete_kalman_state" /app/src/services/redis_service.py | head -20
echo "=== note: bot process must be restarted to load module; apply expire to keys anyway ==="
docker exec -i trading-bot-bot-1 python3 - <<'PY'
import asyncio
from src.services.redis_service import redis_service
async def main():
    c = redis_service._get_instance().client
    await c.ping()
    cursor = 0
    updated = already = 0
    TTL = 1209600
    while True:
        cursor, keys = await c.scan(cursor=cursor, match="kalman:*", count=100)
        for key in keys:
            ttl = await c.ttl(key)
            if ttl < 0:
                await c.expire(key, TTL)
                updated += 1
            else:
                already += 1
                # refresh sliding window for active keys
                await c.expire(key, TTL)
        if cursor == 0:
            break
    mem = await c.config_get("maxmemory")
    pol = await c.config_get("maxmemory-policy")
    print(f"kalman_ttl_refreshed updated_from_none={updated} refreshed={already}")
    print("maxmemory", mem, "policy", pol)
asyncio.run(main())
PY
echo "=== DONE ==="
