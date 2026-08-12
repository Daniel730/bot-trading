#!/usr/bin/env bash
# Convenience wrapper for the Daily Bot Audit.
# Reproducible, versioned, observable, idempotent, easy to run manually or from cron.
#
# Usage:
#   ./scripts/run_daily_audit.sh                 # fast gate, read-only (default)
#   ./scripts/run_daily_audit.sh full            # add heavy monitor safety tests
#   ./scripts/run_daily_audit.sh fast --autofix  # allow safe hygiene auto-remediation
#
# The audit never trades, never flips PAPER_TRADING, never touches credentials.
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

SCOPE="${1:-fast}"
shift || true
EXTRA=("$@")

# Prefer the project venv; fall back to system python.
if [ -x .venv/Scripts/python.exe ]; then
  PY=.venv/Scripts/python.exe
elif [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
else
  PY=python3
fi

export PYTHONPATH="$(pwd)"

echo "=== Daily Bot Audit ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="
"$PY" scripts/daily_bot_audit.py --tests "$SCOPE" "${EXTRA[@]}"
rc=$?
echo "=== audit exit code: $rc (0=HEALTHY 1=DEGRADED 2=CRITICAL) ==="
exit $rc
