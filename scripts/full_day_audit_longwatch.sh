#!/usr/bin/env bash
set -euo pipefail
cd /workspace
LOG=data/audit/logs/longwatch.out
END=$(( $(date +%s) + 8*3600 ))
echo "longwatch_start $(date -u -Iseconds) end_epoch=$END" | tee -a "$LOG"
monitor_pid() {
  pgrep -f '[.]venv/bin/python src/monitor.py' | head -1 || true
}
while (( $(date +%s) < END )); do
  {
    echo "==== $(date -u -Iseconds) ===="
    PYTHONPATH=/workspace .venv/bin/python -c 'from scripts.full_day_audit_analyzer import analyze; import json; print(json.dumps(analyze(), indent=2))'
    pid=$(monitor_pid)
    if [[ -n "$pid" ]]; then
      ps -o pid,rss,etime,cmd -p "$pid"
    else
      echo "ALERT monitor down — attempting restart"
      tmux -f /exec-daemon/tmux.portal.conf send-keys -t "audit-monitor:0.0" 'cd /workspace && PYTHONPATH=/workspace .venv/bin/python src/monitor.py 2>&1 | tee -a data/audit/logs/monitor.out' C-m || true
    fi
    if [[ -f data/audit/logs/monitor.out ]]; then
      sz=$(stat -c%s data/audit/logs/monitor.out)
      if (( sz > 50000000 )); then
        tail -c 20000000 data/audit/logs/monitor.out > data/audit/logs/monitor.out.tmp
        mv data/audit/logs/monitor.out.tmp data/audit/logs/monitor.out
        echo "rotated monitor.out size was $sz"
      fi
    fi
  } | tee -a "$LOG"
  sleep 900
done
echo "longwatch_end $(date -u -Iseconds)" | tee -a "$LOG"
