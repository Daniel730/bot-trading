#!/usr/bin/env bash
# Probe sec-worker health + Redis fundamental cache freshness. No secrets printed.
set -euo pipefail
echo "=== SEC CACHE PROBE $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

echo "--- sec-worker ---"
docker inspect trading-bot-sec-worker-1 --format \
  'Status={{.State.Status}} OOM={{.State.OOMKilled}} RC={{.RestartCount}} Started={{.State.StartedAt}} Exit={{.State.ExitCode}} Mem={{.HostConfig.Memory}}' \
  2>&1 || echo "MISSING trading-bot-sec-worker-1"

echo "--- recent sec-worker logs ---"
docker logs trading-bot-sec-worker-1 --tail 50 2>&1 | tail -50 || true

echo "--- redis fundamental keys (via bot container) ---"
docker exec trading-bot-bot-1 python3 - <<'PY'
import asyncio
import json
import time

async def main():
    from src.services.redis_service import redis_service
    client = redis_service._get_instance().client
    keys = await client.keys("sec:integrity:*")
    now = time.time()
    print(f"count={len(keys)}")
    stale = 0
    missing_ts = 0
    for raw in sorted(keys)[:40]:
        key = raw.decode() if isinstance(raw, bytes) else raw
        ttl = await client.ttl(raw)
        payload = await client.get(raw)
        age = None
        source = None
        score = None
        if payload:
            try:
                data = json.loads(payload)
                score = data.get("score")
                source = data.get("source")
                ts = data.get("last_updated")
                if isinstance(ts, (int, float)) and ts > 1_000_000_000:
                    age = int(now - float(ts))
                elif ts is not None:
                    missing_ts += 1
                    age = f"non_wall_clock:{ts}"
                else:
                    missing_ts += 1
            except Exception as exc:
                print(f"{key} parse_error={exc}")
                continue
        if isinstance(age, int) and age > 86400:
            stale += 1
        print(f"{key} ttl={ttl} score={score} source={source} age_s={age}")
    print(f"summary stale_gt_24h={stale} bad_or_missing_ts={missing_ts}")

asyncio.run(main())
PY
