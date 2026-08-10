#!/usr/bin/env bash
# Post-deploy / soak health probe for bot-server (no secrets printed).
# Incorporates checks previously drafted as infra/_final_health.sh.
set +e
echo "=== POSTDEPLOY HEALTH $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

echo "=== bot ==="
BOT_STATE="$(docker inspect trading-bot-bot-1 --format '{{.State.Status}}' 2>/dev/null || echo missing)"
if [ "$BOT_STATE" != "running" ]; then
  echo "FAIL: trading-bot-bot-1 is not running (state=${BOT_STATE})"
  exit 1
fi
docker inspect trading-bot-bot-1 --format 'Restart={{.RestartCount}} OOM={{.State.OOMKilled}} Status={{.State.Status}} RestartPolicy={{.HostConfig.RestartPolicy.Name}} Image={{.Config.Image}} Started={{.State.StartedAt}}'
docker exec trading-bot-bot-1 python -c 'from src import config; s=config.settings; print("discovery=", s.PAIR_DISCOVERY_ENABLED); print("paper=", s.PAPER_TRADING); print("broker_paper=", s.is_broker_paper_trading); print("auto_approve=", s.should_auto_approve_trades); print("pass_rate=", getattr(s,"COINTEGRATION_ROLLING_PASS_RATE",None)); print("max_active=", getattr(s,"MAX_ACTIVE_PAIRS",None)); print("entry_z=", s.MONITOR_ENTRY_ZSCORE)'

echo "=== active count ==="
docker exec trading-bot-postgres-1 psql -U bot_admin -d trading_bot -Atc "SELECT count(*) FROM trading_pairs WHERE status='Active';" 2>/dev/null \
  || echo "active_count=unavailable"

echo "=== binds (redis/postgres/mcp/grpc must be loopback) ==="
ss -tuln | awk 'NR>1 && /:(6379|5433|8000|50051) / {print $5}'
bad=$(ss -tuln | awk 'NR>1 && /:(6379|5433|8000|50051) / {print $5}' | grep -vE '^127\.0\.0\.1:' || true)
if [ -n "$bad" ]; then echo "FAIL_public=$bad"; else echo "public_bind_ok=yes"; fi

echo "=== redis ==="
# AUTH may be required; PING without password failing is expected — never print the password.
docker exec trading-bot-redis-1 redis-cli PING 2>&1 | head -1

echo "=== rss ==="
docker exec trading-bot-bot-1 awk '/VmRSS/ {print}' /proc/1/status

echo "=== frontend markers ==="
docker inspect trading-bot-frontend-1 --format 'Created={{.Created}} Started={{.State.StartedAt}} Image={{.Config.Image}}' 2>/dev/null
JS=$(docker exec trading-bot-frontend-1 sh -c 'ls /usr/share/nginx/html/assets/*.js 2>/dev/null | head -1')
echo "js=$JS"
if [ -n "$JS" ]; then
  docker exec trading-bot-frontend-1 sh -c "grep -c qrserver '$JS' || true; grep -c 'never leaves this browser' '$JS' || true"
fi

echo "=== sec integrity keys ==="
docker exec trading-bot-bot-1 python -c 'import asyncio
async def main():
  from src.services.redis_service import redis_service
  keys=await redis_service.client.keys("sec:integrity:*")
  print("sec_integrity_count=", len(keys))
asyncio.run(main())' 2>&1 | tail -5

echo "=== recent errors (15m) ==="
docker logs trading-bot-bot-1 --since 15m 2>&1 | grep -EIE 'Traceback|Startup blocked|CRITICAL|OOMKilled' | tail -20 \
  || echo "no_critical_matches"

echo "=== scan sample ==="
docker logs trading-bot-bot-1 --since 15m 2>&1 | grep -E 'SCAN \[' | tail -5 \
  || echo "no_scan_lines"

echo "HEALTH_PROBE_DONE"
