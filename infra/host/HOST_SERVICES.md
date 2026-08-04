# bot-server host services inventory

Generated for the Phase 3 infra hygiene pass. Update when ports or compose paths change.

## Host

| Item | Value |
|---|---|
| Hostname | `bot-server` |
| OS | RHEL 9 (`el9`) |
| CPU | 4 cores |
| RAM | 7.4 GiB |
| System disk | 128 GB SSD (LVM: `/` 70G, `/home` 40G) |
| Data HDD | `/mnt/data` when attached (`infra/host/setup_hdd.sh`) |
| Tailscale | `tailscaled.service` |

## Resource policy (Phase 0)

| Workload | Limit |
|---|---|
| Minecraft | `-Xmx2G`, systemd `MemoryMax=2800M`, `CPUQuota=150%`, view/sim distance 8 |
| trading-bot `bot` | `mem_limit: 1280m`, `cpus: 1.50` |
| trading-bot `sec-worker` | `640m` / `0.75` |
| trading-bot `execution-engine` | `512m` / `0.75` |
| trading-bot `postgres` | `512m` / `1.0` |
| trading-bot `redis` | `128m` / `0.50` |
| trading-bot `frontend` | `64m` / `0.25` |
| GH Actions runner | single `actions-runner.service` (user systemd) |

## Running services

| Name | How | Ports | Compose / unit | Notes |
|---|---|---|---|---|
| Minecraft | user systemd + tmux | game port (default 25565) | `~/.config/systemd/user/minecraft.service` | cwd `/home/daniel/mineserver` |
| trading-bot stack | Docker Compose | 3000, 8082, 8000, 50051, 5433, 6379 | runner worktree `infra/docker-compose.*.yml` | project `trading-bot` |
| Nextcloud | Docker Compose | 8090 | `~/docker/compose/nextcloud` | data under compose `dados` until HDD migrate |
| Nginx Proxy Manager | Docker Compose | 80, 81, 443 | `~/docker/compose/npm` | public ingress |
| AdGuard Home | Docker Compose | 53, 3001 | `~/docker/compose/adguardhome` | migrate to Pi (Phase 2) |
| GH Actions runner | user systemd | — | `actions-runner.service` | one listener only |
| Odysseus | Docker Compose | 7000 | `~/docker/compose/odysseus` | Often running; soft-cap via `infra/ops_apply_host_soft_limits.sh` |
| Stremio | Podman | — | — | stopped |
| node-exporter | Docker (optional) | 9100 | `infra/host/docker-compose.node-exporter.yml` | host metrics |

## Docker networks

Preferred shared nets (create with `ensure_docker_networks.sh`):

- `edge` — NPM / public reverse proxy
- `apps` — application containers
- `data` — DB sidecars if attached across stacks

Existing external `proxy` network is used by AdGuard/NPM today; leave it until stacks are re-wired.

## Ops scripts (`infra/host/`)

| Script | Purpose |
|---|---|
| `apply_phase0_mine.sh` | Mine heap/props/systemd + cleanup |
| `setup_hdd.sh` | Format mount + fstab for HDD |
| `migrate_to_hdd.sh` | Nextcloud + archives → `/mnt/data` |
| `daily_backup.sh` | Postgres dump + world tar |
| `memory_alert.sh` | RAM/swap Telegram/syslog alert |
| `ensure_docker_networks.sh` | Create `edge`/`apps`/`data` |
| `docker-compose.pi-edge.yml` | AdGuard + exporter for Pi |
| `PI_EDGE.md` | Pi cutover guide |
| `REASSESS_K8S.md` | Phase 4 decision checklist |

## Alerting

User systemd timer `host-memory-alert.timer` runs `memory_alert.sh` every 5 minutes.
Optional: export `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` in `~/.config/host-alerts.env`.
