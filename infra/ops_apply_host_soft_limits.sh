#!/usr/bin/env bash
# Soft-cap shared-host Docker stacks that lack compose mem_limit (no recreate, no volume wipe).
# Safe to re-run. Does NOT touch trading-bot (compose already sets limits).
set -euo pipefail

apply() {
  local name="$1" mem="$2" cpus="$3"
  if ! docker inspect "$name" >/dev/null 2>&1; then
    echo "skip missing $name"
    return 0
  fi
  local cur
  cur=$(docker inspect "$name" --format '{{.HostConfig.Memory}}')
  if [[ "$cur" != "0" && "$cur" != "" ]]; then
    echo "keep $name existing Memory=$cur"
    return 0
  fi
  echo "update $name memory=$mem cpus=$cpus"
  docker update --memory="$mem" --memory-swap="$mem" --cpus="$cpus" "$name" >/dev/null
  docker inspect "$name" --format '{{.Name}} mem={{.HostConfig.Memory}} nano_cpus={{.HostConfig.NanoCpus}}'
}

# Conservative caps for non-trading stacks on ~7.4GiB host.
apply adguardhome 512m 0.50
apply nginx-proxy-manager 256m 0.50
apply nextcloud-app-1 384m 0.50
apply nextcloud-db-1 384m 0.50
apply odysseus-odysseus-1 512m 0.75
apply odysseus-searxng-1 256m 0.40
apply odysseus-ntfy-1 96m 0.20
apply odysseus-chromadb-1 256m 0.40

echo "--- after ---"
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}' | head -40
echo "SOFT_LIMITS_APPLIED"
