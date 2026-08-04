#!/usr/bin/env bash
# Read-only security posture probe for bot-server. Never prints secret values.
set -euo pipefail

ENVF="${ENVF:-/home/daniel/.env.trading}"

echo "=== .env.trading perms ==="
ls -la "$ENVF" "${ENVF}".bak.* 2>/dev/null | head -5 || true

echo "=== safe trading flags only ==="
python3 - "$ENVF" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
keys = {
    "PAPER_TRADING",
    "LIVE_CAPITAL_DANGER",
    "DEV_MODE",
    "BROKERAGE_PROVIDER",
    "ALPACA_BASE_URL",
    "APCA_API_BASE_URL",
    "DASHBOARD_ALLOWED_ORIGINS",
    "DASHBOARD_ALLOWED_ORIGIN_REGEX",
    "DRY_RUN",
    "IGNORE_UNMANAGED_POSITIONS",
    "BOT_HOST_PORT",
    "APP_ENV_FILE",
}
vals = {}
for line in p.read_text(errors="replace").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    vals[k.strip()] = v.strip().strip('"').strip("'")
for k in sorted(keys):
    print(f"{k}={vals.get(k, 'MISSING')}")
url = (vals.get("ALPACA_BASE_URL") or vals.get("APCA_API_BASE_URL") or "").lower()
host = url.split("//")[-1].split("/")[0] if url else "MISSING"
print(f"alpaca_host={host}")
print(f"is_live_money_endpoint={host == 'api.alpaca.markets'}")
print(f"is_paper_endpoint={host == 'paper-api.alpaca.markets'}")
weak = {"changeme", "password", "secret", "arbi-elite-2026", "bot_pass", "your_bot_token", "bot_dev_secret"}
for k in (
    "DASHBOARD_TOKEN",
    "POSTGRES_PASSWORD",
    "ALPACA_API_KEY",
    "ALPACA_API_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "REDIS_PASSWORD",
):
    v = vals.get(k)
    if v is None:
        print(f"{k}_status=MISSING")
    elif len(v) < 8:
        print(f"{k}_status=SHORT len={len(v)}")
    elif v.lower() in weak:
        print(f"{k}_status=WEAK_DEFAULT")
    else:
        print(f"{k}_status=OK len={len(v)}")
PY

echo "=== container security posture (no env secrets) ==="
# mcp-server / execution-engine are optional-profile sidecars — tolerate absence.
for c in trading-bot-bot-1 trading-bot-postgres-1 trading-bot-redis-1 trading-bot-frontend-1; do
  echo "--- $c ---"
  docker inspect "$c" --format 'User={{json .Config.User}} Privileged={{json .HostConfig.Privileged}} ReadonlyRootfs={{json .HostConfig.ReadonlyRootfs}} CapAdd={{json .HostConfig.CapAdd}} CapDrop={{json .HostConfig.CapDrop}} NetworkMode={{json .HostConfig.NetworkMode}}' \
    2>/dev/null || echo "MISSING $c"
done
for c in trading-bot-mcp-server-1 trading-bot-execution-engine-1; do
  echo "--- $c (optional) ---"
  docker inspect "$c" --format 'User={{json .Config.User}} Privileged={{json .HostConfig.Privileged}} ReadonlyRootfs={{json .HostConfig.ReadonlyRootfs}} CapAdd={{json .HostConfig.CapAdd}} CapDrop={{json .HostConfig.CapDrop}} NetworkMode={{json .HostConfig.NetworkMode}}' \
    2>/dev/null || echo "SKIP $c (optional profile not deployed)"
done

echo "=== bot SAFE env flags ==="
docker inspect trading-bot-bot-1 --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(PAPER_TRADING|LIVE_CAPITAL_DANGER|DEV_MODE|BROKERAGE_PROVIDER|ALPACA_BASE_URL|APCA_API_BASE_URL|DRY_RUN|IGNORE_UNMANAGED|DASHBOARD_ALLOWED)=' || true

echo "=== execution-engine SAFE env (optional) ==="
if docker inspect trading-bot-execution-engine-1 >/dev/null 2>&1; then
  docker inspect trading-bot-execution-engine-1 --format '{{range .Config.Env}}{{println .}}{{end}}' \
    | grep -E '^(DRY_RUN|LIVE_CAPITAL_DANGER|PAPER_TRADING|ALPACA_BASE_URL)=' || true
else
  echo "SKIP execution-engine (optional profile not deployed)"
fi

echo "=== published ports of interest ==="
ss -tuln 2>/dev/null | awk 'NR==1 || /:(6379|5433|8082|8000|3000|50051|5432) /'

echo "=== redis auth check (no password leak) ==="
if docker exec trading-bot-redis-1 redis-cli PING 2>&1 | grep -qi NOAUTH; then
  echo "redis_requirepass_set=yes"
elif docker exec trading-bot-redis-1 sh -c \
  'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning CONFIG GET requirepass' \
  2>/dev/null | awk 'NR==2 {exit length($0)==0}'; then
  echo "redis_requirepass_set=yes"
else
  echo "redis_requirepass_set=no"
fi

echo "=== hardened host publishes ==="
ss -tuln 2>/dev/null | awk 'NR > 1 && /:(6379|5433|8000|50051) / { print $5 }' | while read -r loc; do
  case "$loc" in
    127.0.0.1:*) echo "ok_loopback $loc" ;;
    *) echo "BAD_PUBLIC $loc" ;;
  esac
done

echo "=== postgres auth method (pg_hba excerpt) ==="
docker exec trading-bot-postgres-1 sh -c 'grep -E "host|local" /var/lib/postgresql/data/pg_hba.conf 2>/dev/null | head -20' || true

echo "=== dashboard runtime mode via ping/local ==="
curl -sS --max-time 5 http://127.0.0.1:8082/ping || true
echo
