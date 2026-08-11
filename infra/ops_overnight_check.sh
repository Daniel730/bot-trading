#!/usr/bin/env bash
# Overnight ops check — no secrets printed. Run on bot-server or via ssh.
set -euo pipefail

ENV_FILE="${APP_ENV_FILE:-/home/daniel/.env.trading}"
BOT_PORT="${BOT_HOST_PORT:-8082}"

echo "=== OPS CHECK $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "--- host ---"
hostname
uptime
free -h | head -3

echo "--- oom ---"
if command -v journalctl >/dev/null 2>&1; then
  journalctl -k --since "6 hours ago" --no-pager 2>/dev/null | grep -iE "oom|killed process|Out of memory" | tail -15 || true
fi
dmesg -T 2>/dev/null | grep -iE "oom|killed process|Out of memory" | tail -10 || true

echo "--- containers ---"
docker ps -a --filter name=trading-bot --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
for svc in trading-bot-bot-1 trading-bot-sec-worker-1 trading-bot-redis-1 trading-bot-postgres-1; do
  docker inspect "$svc" --format '{{.Name}} state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}} started={{.State.StartedAt}} rc={{.RestartCount}} oom={{.State.OOMKilled}}' 2>/dev/null || echo "MISSING $svc"
done
for svc in trading-bot-mcp-server-1 trading-bot-execution-engine-1; do
  docker inspect "$svc" --format '{{.Name}} state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}} started={{.State.StartedAt}} rc={{.RestartCount}} oom={{.State.OOMKilled}}' 2>/dev/null || echo "SKIP $svc (optional profile not deployed)"
done

BOT_STATE="$(docker inspect trading-bot-bot-1 --format '{{.State.Status}}' 2>/dev/null || echo missing)"
if [ "$BOT_STATE" != "running" ]; then
  echo "FAIL: trading-bot-bot-1 is not running (state=${BOT_STATE})"
  exit 1
fi
RESTART_POLICY="$(docker inspect trading-bot-bot-1 --format '{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null || echo unknown)"
echo "bot_restart_policy=${RESTART_POLICY}"

echo "--- mem ---"
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}' | head -40
echo "--- trading-bot cgroup limits (0 mem = UNLIMITED) ---"
for svc in trading-bot-bot-1 trading-bot-sec-worker-1; do
  docker inspect "$svc" --format '{{.Name}} mem={{.HostConfig.Memory}} nano_cpus={{.HostConfig.NanoCpus}} oom={{.State.OOMKilled}}' 2>/dev/null || echo "MISSING $svc"
done
for svc in trading-bot-mcp-server-1 trading-bot-execution-engine-1; do
  docker inspect "$svc" --format '{{.Name}} mem={{.HostConfig.Memory}} nano_cpus={{.HostConfig.NanoCpus}} oom={{.State.OOMKilled}}' 2>/dev/null || echo "SKIP $svc (optional)"
done

echo "--- env non-secret ---"
python3 - <<'PY'
from pathlib import Path
vals = {}
for raw in Path("/home/daniel/.env.trading").read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    if line.startswith("export "):
        line = line[len("export "):].strip()
    k, v = line.split("=", 1)
    vals[k.strip()] = v.strip().strip('"').strip("'")
for key in (
    "BOT_HOST_PORT",
    "ORCHESTRATOR_TIMEOUT_SECONDS",
    "MONITOR_ENTRY_ZSCORE",
    "PAPER_TRADING",
    "DEV_MODE",
    "LIVE_CAPITAL_DANGER",
    "BROKERAGE_PROVIDER",
    "ALPACA_BASE_URL",
    "IGNORE_UNMANAGED_POSITIONS",
    "IMAGE_OWNER",
    "IMAGE_TAG",
    "PAIR_DISCOVERY_ENABLED",
    "PAIR_DISCOVERY_MAX_TICKERS",
    "PAIR_DISCOVERY_AUTO_PROMOTE",
    "PAIR_DENYLIST",
):
    print(f"{key}={vals.get(key, '<unset>')}")
for k in ("ALPACA_API_KEY", "ALPACA_API_SECRET", "DASHBOARD_TOKEN", "POSTGRES_PASSWORD", "POLYGON_API_KEY", "TELEGRAM_BOT_TOKEN"):
    v = vals.get(k, "")
    print(f"{k}_set={bool(v) and v not in ('your_bot_token', 'changeme', '')}")
z = float(vals.get("MONITOR_ENTRY_ZSCORE", "2.0") or "2.0")
if z < 1.0:
    raise SystemExit("BAD MONITOR_ENTRY_ZSCORE")
PY

echo "--- runtime inside bot ---"
docker exec trading-bot-bot-1 python3 - <<'PY'
from src.config import settings
print(f"MONITOR_ENTRY_ZSCORE={settings.MONITOR_ENTRY_ZSCORE}")
print(f"ORCHESTRATOR_TIMEOUT_SECONDS={settings.ORCHESTRATOR_TIMEOUT_SECONDS}")
print(f"DEV_MODE={settings.DEV_MODE}")
print(f"PAPER_TRADING={settings.PAPER_TRADING}")
print(f"LIVE_CAPITAL_DANGER={getattr(settings, 'LIVE_CAPITAL_DANGER', None)}")
print(f"BROKERAGE_PROVIDER={getattr(settings, 'BROKERAGE_PROVIDER', None)}")
print(f"ALPACA_BASE_URL={getattr(settings, 'ALPACA_BASE_URL', None)}")
print(f"broker_paper_trading={getattr(settings, 'broker_paper_trading', None)}")
if settings.MONITOR_ENTRY_ZSCORE < 1.0:
    raise SystemExit("z below minimum")
if settings.ORCHESTRATOR_TIMEOUT_SECONDS < 30:
    raise SystemExit("orch timeout too low")
PY

echo "--- bot_settings safe ---"
docker exec trading-bot-bot-1 python3 - <<'PY'
import json
from pathlib import Path
p = Path("/app/data/bot_settings.json")
if not p.exists():
    print("no bot_settings.json")
else:
    d = json.loads(p.read_text())
    # only print structural / config-ish keys
    for k in sorted(d.keys()):
        kl = k.lower()
        if any(x in kl for x in ("token", "secret", "password", "key", "api")):
            print(f"{k}=<redacted>")
            continue
        v = d[k]
        if isinstance(v, (dict, list)):
            print(f"{k}=<{type(v).__name__} len={len(v)}>")
            if k in ("disabled_pairs", "quarantined_pairs", "pair_blacklist", "pairs", "active_pairs", "PAIR_UNIVERSE"):
                print(f"  sample={str(v)[:500]}")
        else:
            print(f"{k}={v!r}"[:240])
PY

echo "--- health ---"
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${BOT_PORT}/api/system/health" || true)
echo "health_http=${code}"

echo "--- scan/signal/guard (30m) ---"
docker logs trading-bot-bot-1 --since 30m 2>&1 | grep -E 'SCAN \[|SIGNAL |SPREAD GUARD|PAIR SKIP|Iteration Complete|Traceback|CRITICAL|OOM|quarantine|PAPER TRADE|APPROV|FILL|timeout|ERROR' | tail -80

echo "--- crash markers (2h) ---"
docker logs trading-bot-bot-1 --since 2h 2>&1 | grep -iE 'Traceback|Startup blocked|CRITICAL|killed|OOM' | tail -20 || echo "(none)"

echo "--- daily bot audit (read-only, best-effort) ---"
# Runs the consolidated Daily Bot Audit (scripts/daily_bot_audit.py) on this host
# where the bot actually runs. It never trades, never flips PAPER_TRADING, never
# touches credentials. Writes reports/daily-audit/YYYY-MM-DD.md and prints a
# verdict. Failures here do NOT fail the ops check (best-effort observability).
AUDIT_DIR="${AUDIT_DIR:-/home/daniel/bot-trading}"
if [ -x "$(command -v docker)" ] && docker inspect trading-bot-bot-1 >/dev/null 2>&1; then
  if [ -f "${AUDIT_DIR}/scripts/daily_bot_audit.py" ]; then
    # Run inside the bot container where the venv + httpx + logs are present.
    # PYTHONPATH makes the scripts/ package importable; the container's own
    # APP_ENV_FILE is already exported in the deploy, so check_env_safety picks
    # up the real .env.trading automatically. Override AUDIT_LOG_PATH if the
    # structured log lives elsewhere in the container.
    docker exec -e PYTHONPATH="${AUDIT_DIR}:/app" -e AUDIT_LOG_PATH="${AUDIT_LOG_PATH:-/app/logs/structured_logs.jsonl}" \
      trading-bot-bot-1 python3 "${AUDIT_DIR}/scripts/daily_bot_audit.py" \
      --tests none --no-autofix \
      --date "$(date -u +%Y-%m-%d)" || echo "AUDIT: non-zero exit (see report)"
  else
    echo "AUDIT: scripts/daily_bot_audit.py not found at ${AUDIT_DIR}; skipping"
  fi
else
  echo "AUDIT: bot container not present; skipping"
fi

echo "OPS_CHECK_DONE"
