#!/usr/bin/env bash
# Alert when RAM available is low or swap is high.
# Env: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (optional), or writes to syslog.
set -euo pipefail

MIN_AVAIL_MIB="${MIN_AVAIL_MIB:-500}"
MAX_SWAP_MIB="${MAX_SWAP_MIB:-1024}"

read -r _ total used free shared buff cache available < <(free -m | awk '/^Mem:/ {print}')
swap_used=$(free -m | awk '/^Swap:/ {print $3}')

msg=""
if (( available < MIN_AVAIL_MIB )); then
  msg+="RAM available ${available}MiB < ${MIN_AVAIL_MIB}MiB. "
fi
if (( swap_used > MAX_SWAP_MIB )); then
  msg+="Swap used ${swap_used}MiB > ${MAX_SWAP_MIB}MiB. "
fi

if [[ -z "$msg" ]]; then
  exit 0
fi

host=$(hostname)
full="[bot-server memory] ${host}: ${msg}(used=${used}MiB total=${total}MiB)"
logger -t host-memory-alert "$full"
echo "$full"

if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]; then
  curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${full}" >/dev/null || true
fi
