#!/usr/bin/env bash
# Post-deploy smoke checks for bot-server (no secrets printed).
# Run on bot-server after a GitHub Actions deploy, or from a workstation via SSH:
#   ssh daniel@bot-server 'bash -s' < scripts/post_deploy_smoke.sh
set -euo pipefail

ENV_FILE="${APP_ENV_FILE:-/home/daniel/.env.trading}"
BOT_PORT="${BOT_HOST_PORT:-8082}"
COMPOSE_ROOT="${BOT_TRADING_ROOT:-$HOME/actions-runner/_work/bot-trading/bot-trading}"
BACKEND_COMPOSE="$COMPOSE_ROOT/infra/docker-compose.backend.yml"
FRONTEND_COMPOSE="$COMPOSE_ROOT/infra/docker-compose.frontend.yml"

echo "=== POST-DEPLOY SMOKE $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ -f "$ENV_FILE" ]] || fail "missing env file: $ENV_FILE"

echo "--- env keys (non-secret) ---"
python3 - <<'PY'
from pathlib import Path

def load(path: Path) -> dict[str, str]:
    vals: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        vals[k.strip()] = v
    return vals

vals = load(Path("/home/daniel/.env.trading"))
for key in (
    "BOT_HOST_PORT",
    "ORCHESTRATOR_TIMEOUT_SECONDS",
    "MONITOR_ENTRY_ZSCORE",
    "PAPER_TRADING",
    "DEV_MODE",
    "IMAGE_OWNER",
    "IMAGE_TAG",
):
    print(f"{key}={vals.get(key, '<unset>')}")
if float(vals.get("MONITOR_ENTRY_ZSCORE", "2.0")) < 1.0:
    raise SystemExit("MONITOR_ENTRY_ZSCORE is below safe minimum 1.0")
PY

echo "--- container status ---"
if [[ -f "$BACKEND_COMPOSE" ]]; then
  docker compose --env-file "$ENV_FILE" -p trading-bot -f "$BACKEND_COMPOSE" ps bot mcp-server sec-worker execution-engine redis postgres
else
  docker ps --filter name=trading-bot --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
fi

for svc in trading-bot-bot-1 trading-bot-mcp-server-1 trading-bot-redis-1 trading-bot-postgres-1; do
  docker inspect "$svc" --format '{{.Name}} state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' 2>/dev/null \
    || fail "container missing: $svc"
done

echo "--- bot image ---"
docker inspect trading-bot-bot-1 --format 'image={{.Config.Image}}'

echo "--- outbound DNS from bot container ---"
docker exec -i trading-bot-bot-1 python3 - <<'PY'
import socket

hosts = ("paper-api.alpaca.markets", "query1.finance.yahoo.com")
failures: list[str] = []
for host in hosts:
    try:
        infos = socket.getaddrinfo(host, 443)
        print(f"{host}=ok addrs={sorted({i[4][0] for i in infos})[:4]}")
    except OSError as exc:
        print(f"{host}=FAIL {type(exc).__name__}: {exc}")
        failures.append(host)
if failures:
    raise SystemExit(
        "bot container cannot resolve public DNS for: "
        + ", ".join(failures)
        + " (pin dns: [8.8.8.8, 1.1.1.1] in compose; Tailscale MagicDNS alone is not enough)"
    )
PY

echo "--- recent bot logs (no crash loop) ---"
docker logs trading-bot-bot-1 --since 8m 2>&1 | tail -30
if docker logs trading-bot-bot-1 --since 8m 2>&1 | grep -qE 'Startup blocked|Traceback|CRITICAL.*boot'; then
  fail "bot logs show startup failure"
fi

echo "--- scan loop ---"
# Prefer classic SCAN lines; fall back to Iteration Complete (crypto off-hours / quieter logs).
if ! docker logs trading-bot-bot-1 --since 15m 2>&1 | grep -E 'SCAN \[' | tail -5; then
  docker logs trading-bot-bot-1 --since 15m 2>&1 | grep -E 'Iteration Complete' | tail -5 \
    || fail "no SCAN / Iteration Complete lines in last 15 minutes"
fi

echo "--- funnel / activity (best-effort) ---"
docker logs trading-bot-bot-1 --since 30m 2>&1 | grep -E 'FUNNEL ' | tail -5 || true
# During US cash hours, equity SCANs should appear once Active equities are admitted.
if docker logs trading-bot-bot-1 --since 30m 2>&1 | grep -qE 'FUNNEL active_eq=[1-9]'; then
  echo "activity_note=equity Active slots present in FUNNEL"
fi

echo "--- health endpoint (401 without auth is OK) ---"
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${BOT_PORT}/api/system/health" || true)
echo "health_http=${code}"
[[ "$code" == "200" || "$code" == "401" ]] || fail "unexpected health HTTP status: $code"

echo "--- runtime settings inside bot container ---"
docker exec -i trading-bot-bot-1 python3 - <<'PY'
from src.config import settings
import inspect
from src.agents.orchestrator import Orchestrator

print(f"ORCHESTRATOR_TIMEOUT_SECONDS={settings.ORCHESTRATOR_TIMEOUT_SECONDS}")
print(f"MONITOR_ENTRY_ZSCORE={settings.MONITOR_ENTRY_ZSCORE}")
src = inspect.getsource(Orchestrator.ainvoke)
print("crypto_macro_bypass=" + str("if crypto_pair:" in src and 'regime = "BULLISH"' in src))
if settings.ORCHESTRATOR_TIMEOUT_SECONDS < 30:
    raise SystemExit("ORCHESTRATOR_TIMEOUT_SECONDS unexpectedly low")
if settings.MONITOR_ENTRY_ZSCORE < 1.0:
    raise SystemExit("MONITOR_ENTRY_ZSCORE below clamp minimum")
PY

echo "SMOKE_OK"
