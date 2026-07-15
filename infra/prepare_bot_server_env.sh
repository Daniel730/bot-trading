#!/usr/bin/env bash
# Prepare trading deploy env on bot-server without printing secret values.
set -euo pipefail

ENV_FILE="${HOME}/.env.trading"
SRC_ENV="${1:-}"

if [[ -n "$SRC_ENV" ]]; then
  cp "$SRC_ENV" "$ENV_FILE"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE (pass a source .env path as arg1)" >&2
  exit 1
fi

chmod 600 "$ENV_FILE"

if grep -q '^BOT_HOST_PORT=' "$ENV_FILE"; then
  sed -i 's/^BOT_HOST_PORT=.*/BOT_HOST_PORT=8082/' "$ENV_FILE"
  echo "UPDATED_BOT_HOST_PORT"
else
  echo 'BOT_HOST_PORT=8082' >> "$ENV_FILE"
  echo "ADDED_BOT_HOST_PORT"
fi

if ! grep -q '^IMAGE_OWNER=' "$ENV_FILE"; then
  echo 'IMAGE_OWNER=daniel730' >> "$ENV_FILE"
  echo "ADDED_IMAGE_OWNER"
fi

docker volume create trading-bot_redis_data >/dev/null
docker volume create trading-bot_postgres_data >/dev/null
docker volume create trading-bot_bot_data >/dev/null
echo "VOLUMES_OK"

python3 - <<'PY'
from pathlib import Path
p = Path("/home/daniel/.env.trading")
vals = {}
for raw in p.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    if line.startswith("export "):
        line = line[len("export "):].strip()
    k, v = line.split("=", 1)
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in {"'", '"'}:
        v = v[1:-1]
    vals[k.strip()] = v.strip()

required = ["POSTGRES_PASSWORD", "DASHBOARD_TOKEN"]
missing = [k for k in required if not vals.get(k)]
print("MISSING:" + ",".join(missing) if missing else "ENV_KEYS_OK")
print("HAS_PAPER_TRADING=" + ("yes" if "PAPER_TRADING" in vals else "no"))
print("BOT_HOST_PORT=" + vals.get("BOT_HOST_PORT", ""))
PY
