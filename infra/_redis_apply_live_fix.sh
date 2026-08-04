#!/usr/bin/env bash
set -euo pipefail
echo "=== discovery/paper flags (redacted) ==="
grep -E '^(PAIR_DISCOVERY_ENABLED|PAPER_TRADING|LIVE_CAPITAL|DEV_MODE)=' /home/daniel/.env.trading || true
echo "=== apply kalman TTL ==="
TTL=1209600
docker exec -i trading-bot-bot-1 python3 - <<PY
import asyncio
from src.services.redis_service import redis_service
TTL = ${TTL}
async def main():
    c = redis_service._get_instance().client
    await c.ping()
    cursor = 0
    updated = already = 0
    while True:
        cursor, keys = await c.scan(cursor=cursor, match="kalman:*", count=100)
        for key in keys:
            ttl = await c.ttl(key)
            if ttl < 0:
                await c.expire(key, TTL)
                updated += 1
            else:
                already += 1
        if cursor == 0:
            break
    print(f"kalman_ttl_applied={updated} already_had_ttl={already} ttl_seconds={TTL}")
    # runtime maxmemory (compose will persist on next redis recreate)
    await c.config_set("maxmemory", "100663296")  # 96mb
    await c.config_set("maxmemory-policy", "volatile-lru")
    mem = await c.config_get("maxmemory")
    pol = await c.config_get("maxmemory-policy")
    print("maxmemory", mem)
    print("policy", pol)
    # verify sample ttl
    cursor, keys = await c.scan(cursor=0, match="kalman:*", count=5)
    for key in keys[:5]:
        print(key, "ttl", await c.ttl(key))
asyncio.run(main())
PY
echo "=== DONE ==="
