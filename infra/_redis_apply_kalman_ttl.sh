#!/usr/bin/env bash
# One-shot: attach sliding TTL to existing kalman:* keys (paper-safe).
# Does not rotate REDIS_PASSWORD. Does not enable pair discovery.
set -euo pipefail
TTL="${KALMAN_STATE_TTL_SECONDS:-1209600}"
docker exec -i trading-bot-bot-1 python3 - <<PY
import asyncio
from src.services.redis_service import redis_service

TTL = int("${TTL}")

async def main():
    c = redis_service._get_instance().client
    await c.ping()
    cursor = 0
    updated = 0
    already = 0
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

asyncio.run(main())
PY
