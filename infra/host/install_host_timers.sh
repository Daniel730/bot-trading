#!/usr/bin/env bash
# Install host timers/units for backups + memory alerts (user systemd).
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
BIN="$HOME/infra-host"
mkdir -p "$BIN" "$HOME/.config/systemd/user"

if [[ "$HERE" != "$BIN" ]]; then
  for f in daily_backup.sh memory_alert.sh ensure_docker_networks.sh setup_hdd.sh migrate_to_hdd.sh; do
    [[ -f "$HERE/$f" ]] && install -m 0755 "$HERE/$f" "$BIN/$f"
  done
else
  chmod +x "$BIN"/*.sh 2>/dev/null || true
fi

cat > "$HOME/.config/systemd/user/host-daily-backup.service" <<EOF
[Unit]
Description=Daily bot-server backups

[Service]
Type=oneshot
ExecStart=$BIN/daily_backup.sh
EOF

cat > "$HOME/.config/systemd/user/host-daily-backup.timer" <<'EOF'
[Unit]
Description=Run daily backups at 04:15

[Timer]
OnCalendar=*-*-* 04:15:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

cat > "$HOME/.config/systemd/user/host-memory-alert.service" <<EOF
[Unit]
Description=Host memory / swap alert

[Service]
Type=oneshot
EnvironmentFile=-%h/.config/host-alerts.env
ExecStart=$BIN/memory_alert.sh
EOF

cat > "$HOME/.config/systemd/user/host-memory-alert.timer" <<'EOF'
[Unit]
Description=Check host memory every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now host-daily-backup.timer host-memory-alert.timer
systemctl --user list-timers --no-pager | grep host- || true
echo "Installed user timers. Optional: echo TELEGRAM_BOT_TOKEN=... > ~/.config/host-alerts.env"
