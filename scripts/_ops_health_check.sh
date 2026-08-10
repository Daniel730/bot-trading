#!/usr/bin/env bash
# Periodic ops health check for bot-server (no secrets printed).
set -euo pipefail
ssh -o ConnectTimeout=15 daniel@bot-server bash -s <<'EOF'
set -euo pipefail
echo "=== OPS CHECK $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
docker ps --filter name=trading-bot-bot-1 --format 'bot={{.Names}} status={{.Status}}'
BOT_STATE="$(docker inspect trading-bot-bot-1 --format '{{.State.Status}}' 2>/dev/null || echo missing)"
if [ "$BOT_STATE" != "running" ]; then
  echo "FAIL: trading-bot-bot-1 is not running (state=${BOT_STATE})"
  exit 1
fi
docker logs trading-bot-bot-1 --since 12m 2>&1 | grep -E 'RISK APPROVED|PARTIAL EXPOSURE|Duplicate entry|Startup blocked|INVENTORY GUARD|CRITICAL|Gross=' | tail -25 || true
docker exec trading-bot-bot-1 python - <<'PY' 2>/dev/null || echo 'alpaca_probe=failed'
import asyncio
from src.services.brokerage_service import BrokerageService

async def main():
    b = BrokerageService()
    cash = await b.get_account_cash()
    eq = await b.get_account_equity()
    positions = await b.get_positions()
    print(f"alpaca cash={cash:.2f} equity={eq:.2f} positions={len(positions)}")
    for p in sorted(positions, key=lambda x: abs(float(x.get('marketValue') or 0)), reverse=True)[:8]:
        print(f"  {p.get('ticker')} qty={p.get('quantity')} mv={float(p.get('marketValue') or 0):.2f}")

asyncio.run(main())
PY
EOF
