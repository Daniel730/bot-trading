#!/usr/bin/env bash
# Remote Redis key lifecycle audit (no password values printed).
set -euo pipefail
echo "=== redis auth ==="
if docker exec trading-bot-redis-1 redis-cli PING 2>&1 | grep -qi NOAUTH; then
  echo "redis_requirepass_set=yes"
else
  echo "redis_requirepass_set=maybe_not"
  docker exec trading-bot-redis-1 redis-cli PING 2>&1 | head -3 || true
fi
echo "=== bot redis ping + key audit ==="
docker exec -i trading-bot-bot-1 python3 - <<'PY'
import asyncio, collections
from src.services.redis_service import redis_service

async def main():
    c = redis_service._get_instance().client
    try:
        pong = await c.ping()
        print(f"bot_redis_ping={pong}")
    except Exception as e:
        print(f"bot_redis_ping_error={type(e).__name__}:{e}")
        return
    info = await c.info("memory")
    print(f"used_memory_human={info.get('used_memory_human')}")
    print(f"maxmemory={info.get('maxmemory')}")
    print(f"maxmemory_policy={info.get('maxmemory_policy')}")
    dbsize = await c.dbsize()
    print(f"dbsize={dbsize}")
    prefixes = collections.Counter()
    ttl_stats = collections.defaultdict(lambda: {"with_ttl": 0, "no_ttl": 0, "ttls": []})
    cursor = 0
    scanned = 0
    while True:
        cursor, keys = await c.scan(cursor=cursor, count=200)
        for key in keys:
            scanned += 1
            if key.startswith("sec:integrity:"):
                prefix = "sec:integrity"
            elif key.startswith("execution_attempt"):
                prefix = key.split(":", 1)[0]
            elif key.startswith("l2:"):
                parts = key.split(":")
                prefix = ":".join(parts[:2]) if len(parts) > 1 else key.split(":", 1)[0]
            elif key.startswith("cache:"):
                prefix = "cache"
            elif key.startswith("whale:"):
                parts = key.split(":")
                prefix = ":".join(parts[:2]) if len(parts) > 1 else key.split(":", 1)[0]
            elif key.startswith("entropy_baseline"):
                prefix = "entropy_baseline"
            elif key.startswith("ratelimit:"):
                prefix = "ratelimit"
            elif key.startswith("execution:"):
                parts = key.split(":")
                prefix = ":".join(parts[:2])
            else:
                prefix = key.split(":", 1)[0] if ":" in key else key
            prefixes[prefix] += 1
            ttl = await c.ttl(key)
            if ttl < 0:
                ttl_stats[prefix]["no_ttl"] += 1
            else:
                ttl_stats[prefix]["with_ttl"] += 1
                ttl_stats[prefix]["ttls"].append(ttl)
        if cursor == 0:
            break
    print(f"scanned={scanned}")
    print("--- prefix counts ---")
    for p, n in prefixes.most_common():
        st = ttl_stats[p]
        max_ttl = max(st["ttls"]) if st["ttls"] else None
        min_ttl = min(st["ttls"]) if st["ttls"] else None
        print(
            f"{p}\tcount={n}\twith_ttl={st['with_ttl']}\tno_ttl={st['no_ttl']}"
            f"\tmin_ttl={min_ttl}\tmax_ttl={max_ttl}"
        )
    print("--- sample no-ttl keys (up to 40) ---")
    shown = 0
    cursor = 0
    while shown < 40:
        cursor, keys = await c.scan(cursor=cursor, count=200)
        for key in keys:
            ttl = await c.ttl(key)
            if ttl < 0:
                typ = await c.type(key)
                print(f"no_ttl key={key} type={typ} ttl={ttl}")
                shown += 1
                if shown >= 40:
                    break
        if cursor == 0:
            break
    print("--- sec integrity ---")
    ks = []
    cursor = 0
    while True:
        cursor, batch = await c.scan(cursor=cursor, match="sec:integrity:*", count=100)
        ks.extend(batch)
        if cursor == 0:
            break
    print(f"sec:integrity count={len(ks)}")
    for k in ks[:5]:
        print(k, "ttl", await c.ttl(k))
    print("--- kalman ---")
    ks = []
    cursor = 0
    while True:
        cursor, batch = await c.scan(cursor=cursor, match="kalman:*", count=100)
        ks.extend(batch)
        if cursor == 0:
            break
    print(f"kalman count={len(ks)}")
    for k in ks[:15]:
        print(k, "ttl", await c.ttl(k))

asyncio.run(main())
PY
echo "=== env redis password len ==="
python3 - <<'PY'
from pathlib import Path
p = Path("/home/daniel/.env.trading")
val = ""
for line in p.read_text().splitlines():
    if line.startswith("REDIS_PASSWORD="):
        val = line.split("=", 1)[1]
        break
print("REDIS_PASSWORD_LEN", len(val))
print("REDIS_PASSWORD_SET", bool(val))
PY
echo "=== container REDIS_PASSWORD lens ==="
for c in trading-bot-bot-1 trading-bot-sec-worker-1 trading-bot-mcp-server-1 trading-bot-execution-engine-1 trading-bot-redis-1; do
  len=$(docker exec "$c" sh -c 'printf %s "$REDIS_PASSWORD" | wc -c' 2>/dev/null || echo ERR)
  echo "$c REDIS_PASSWORD_LEN=$len"
done
echo "=== DONE ==="
