#!/usr/bin/env bash
# Apply paper activity knobs on bot-server (no secrets printed).
set -euo pipefail
ENV_FILE="${APP_ENV_FILE:-/home/daniel/.env.trading}"
BACKUP="${ENV_FILE}.bak_activity_$(date -u +%Y%m%d_%H%M%S)"

cp -a "$ENV_FILE" "$BACKUP"
echo "backup=$BACKUP"

python3 - <<'PY'
from pathlib import Path
path = Path("/home/daniel/.env.trading")
replacements = {
    "COINTEGRATION_ROLLING_PASS_RATE": "0.40",
    "MAX_ACTIVE_PAIRS": "20",
    "MONITOR_ENTRY_ZSCORE": "1.75",
    "PAIR_DISCOVERY_ENABLED": "false",
    "PAIR_DISCOVERY_AUTO_PROMOTE": "false",
}
text = path.read_text(encoding="utf-8")
lines = []
seen: set[str] = set()
for line in text.splitlines(keepends=True):
    raw = line.strip()
    if raw and not raw.startswith("#") and "=" in raw:
        key = raw.split("=", 1)[0].strip()
        if key in replacements:
            nl = "\n" if line.endswith("\n") else ""
            lines.append(f"{key}={replacements[key]}{nl}")
            seen.add(key)
            continue
    lines.append(line)
if lines and not str(lines[-1]).endswith("\n"):
    lines[-1] = str(lines[-1]) + "\n"
for key, val in replacements.items():
    if key not in seen:
        lines.append(f"{key}={val}\n")
path.write_text("".join(lines), encoding="utf-8")
print("updated", sorted(replacements))
PY

grep -E '^(COINTEGRATION_ROLLING_PASS_RATE|MAX_ACTIVE_PAIRS|MONITOR_ENTRY_ZSCORE|PAIR_DISCOVERY_ENABLED|PAIR_DISCOVERY_AUTO_PROMOTE)=' "$ENV_FILE"

export APP_ENV_FILE="$ENV_FILE"
cd "${BOT_TRADING_ROOT:-$HOME/actions-runner/_work/bot-trading/bot-trading}"
docker compose --env-file "$ENV_FILE" -p trading-bot -f infra/docker-compose.backend.yml \
  up -d --no-deps --force-recreate bot sec-worker

echo "waiting for bot..."
sleep 20
docker inspect trading-bot-bot-1 --format 'Restart={{.RestartCount}} Status={{.State.Status}} Started={{.State.StartedAt}}'
docker exec -i trading-bot-bot-1 python3 <<'PY'
from src.config import settings as s
print("pass_rate", s.COINTEGRATION_ROLLING_PASS_RATE)
print("max_active", s.MAX_ACTIVE_PAIRS)
print("entry_z", s.MONITOR_ENTRY_ZSCORE)
print("discovery", s.PAIR_DISCOVERY_ENABLED, s.PAIR_DISCOVERY_AUTO_PROMOTE)
print("broker_paper", s.is_broker_paper_trading)
PY
