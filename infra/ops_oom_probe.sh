#!/usr/bin/env bash
# OOM / memory baseline probe for bot-server. No secrets printed.
set -euo pipefail

echo "=== OPS OOM PROBE $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "--- host ---"
hostname
uptime
free -h
echo
free -m | awk '/^Mem:/ {printf "mem_used_mib=%s mem_avail_mib=%s mem_total_mib=%s\n",$3,$7,$2} /^Swap:/ {printf "swap_used_mib=%s swap_total_mib=%s\n",$3,$2}'

echo "--- top rss ---"
ps aux --sort=-%mem | awk 'NR==1 || NR<=16 {printf "%s\n",$0}'

echo "--- trading-bot limits ---"
for c in trading-bot-bot-1 trading-bot-mcp-server-1 trading-bot-sec-worker-1 \
         trading-bot-postgres-1 trading-bot-redis-1 trading-bot-frontend-1 \
         trading-bot-execution-engine-1; do
  docker inspect "$c" --format \
    '{{.Name}} status={{.State.Status}} oom={{.State.OOMKilled}} rc={{.RestartCount}} mem={{.HostConfig.Memory}} swap={{.HostConfig.MemorySwap}} nano_cpus={{.HostConfig.NanoCpus}} started={{.State.StartedAt}} exit={{.State.ExitCode}}' \
    2>/dev/null || echo "MISSING $c"
done

echo "--- other stack limits (0 = unlimited) ---"
for c in odysseus-odysseus-1 odysseus-chromadb-1 odysseus-ntfy-1 odysseus-searxng-1 \
         nextcloud-app-1 nextcloud-db-1 nginx-proxy-manager adguardhome; do
  docker inspect "$c" --format '{{.Name}} mem={{.HostConfig.Memory}} nano_cpus={{.HostConfig.NanoCpus}}' \
    2>/dev/null || echo "MISSING $c"
done

echo "--- docker stats ---"
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}\t{{.PIDs}}'

echo "--- env discovery (non-secret) ---"
python3 - <<'PY'
from pathlib import Path
vals = {}
p = Path("/home/daniel/.env.trading")
if not p.exists():
    print("missing .env.trading")
    raise SystemExit(0)
for raw in p.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    if line.startswith("export "):
        line = line[len("export "):].strip()
    k, v = line.split("=", 1)
    vals[k.strip()] = v.strip().strip('"').strip("'")
for key in (
    "PAIR_DISCOVERY_ENABLED",
    "PAIR_DISCOVERY_MAX_TICKERS",
    "PAIR_DISCOVERY_AUTO_PROMOTE",
    "PAIR_DISCOVERY_MAX_ABS_HEDGE",
    "PAIR_DISCOVERY_MIN_ABS_HEDGE",
    "PAIR_DENYLIST",
    "DEV_MODE",
    "PAPER_TRADING",
    "MONITOR_ENTRY_ZSCORE",
    "ORCHESTRATOR_TIMEOUT_SECONDS",
    "BOT_HOST_PORT",
):
    print(f"{key}={vals.get(key, '<unset>')}")
PY

echo "--- runtime inside bot ---"
docker exec trading-bot-bot-1 python3 - <<'PY' || echo "bot exec failed"
from src.config import settings
print("PAIR_DISCOVERY_ENABLED", settings.PAIR_DISCOVERY_ENABLED)
print("PAIR_DISCOVERY_MAX_TICKERS", settings.PAIR_DISCOVERY_MAX_TICKERS)
print("PAIR_DISCOVERY_AUTO_PROMOTE", settings.PAIR_DISCOVERY_AUTO_PROMOTE)
print("PAIR_DISCOVERY_MAX_ABS_HEDGE", settings.PAIR_DISCOVERY_MAX_ABS_HEDGE)
print("PAIR_DISCOVERY_MIN_ABS_HEDGE", settings.PAIR_DISCOVERY_MIN_ABS_HEDGE)
print("DEV_MODE", settings.DEV_MODE)
print("PAPER_TRADING", settings.PAPER_TRADING)
pairs = getattr(settings, "PAIRS", None) or getattr(settings, "ACTIVE_PAIRS", None) or []
try:
    print("pairs_count", len(pairs))
except Exception:
    print("pairs_count", "?")
PY

echo "--- oom journal ---"
if command -v journalctl >/dev/null 2>&1; then
  journalctl -k --since "2026-07-01" --no-pager 2>/dev/null \
    | grep -iE "oom|Out of memory|Killed process" | tail -40 || true
  sudo -n journalctl -k --since "2026-07-01" --no-pager 2>/dev/null \
    | grep -iE "oom|Out of memory|Killed process" | tail -40 || true
fi
dmesg -T 2>/dev/null | grep -iE "oom|Out of memory|Killed process" | tail -20 || true

echo "--- docker oom events (30d) ---"
docker events --since 720h --until 0s --filter event=oom \
  --format '{{.Time}} {{.Action}} {{.Actor.Attributes.name}}' 2>/dev/null | tail -30 || true

echo "--- memory alert timer ---"
systemctl --user is-active host-memory-alert.timer 2>&1 || true
systemctl --user is-enabled host-memory-alert.timer 2>&1 || true
ls -la "$HOME/.local/bin/memory_alert.sh" 2>/dev/null || true
ls -la "$HOME/actions-runner/_work/bot-trading/bot-trading/infra/host/memory_alert.sh" 2>/dev/null || true

echo "--- compose mem_limit on disk ---"
ROOT="${COMPOSE_ROOT:-$HOME/actions-runner/_work/bot-trading/bot-trading}"
grep -n "mem_limit\|cpus:" "$ROOT/infra/docker-compose.backend.yml" 2>/dev/null | head -40 || echo "backend compose missing"
grep -n "mem_limit\|cpus:" "$ROOT/infra/docker-compose.frontend.yml" 2>/dev/null | head -20 || echo "frontend compose missing"

echo "OPS_OOM_PROBE_DONE"
