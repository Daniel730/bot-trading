# Overnight wrap — 2026-08-04 (Portugal)

Standing swarm ended ~09:00. bot-server stayed on **Alpaca paper**. Live `~/.env.trading` was not changed by this wrap.

## Timeline

| Phase | What landed |
|---|---|
| **OOM restart** | Host OOM had killed the monitor (exit 137). Probe/recover runbooks + soft host limits; bot recovered and stayed under the 1.25 GiB cgroup. |
| **Security** | Compose Redis **requirepass** + **loopback** publishes (`127.0.0.1:6379`); FastMCP/Java gRPC loopback harden; `ss` peer false-positive fixed. |
| **Memory history-v2** | Kalman JSON fingerprints → streaming **history-v2**; cache prune / JSONL rotation / `MEMORY_*` (PRs **#96**, **#106**). Morning RSS ~220–360 MiB with scout OFF. |
| **Soft-admit cleanup** | Failed cointegration now **benches** instead of soft-admit. Junk Active rows cleared; issue **#103** closed. |
| **Equity re-admit** | **3 equities + 4 crypto** Active & cointegrated: `GOOGL/GOOG`, `UNH/ELV`, `VLO/MPC` + BTC/ETH, ETH/SOL, AVAX/DOT, AVAX/LTC. Knobs pinned: `COINTEGRATION_ROLLING_PASS_RATE=0.40`, `MAX_ACTIVE_PAIRS=30`. |
| **Clean image deploys** | Hotpatch lag cleared (**#104** closed). Master through **`e26a32d`** / PR **#107** (scout corr floors + hedge persistence) deployed with clean docker diff. |
| **Discovery OFF** | `PAIR_DISCOVERY_ENABLED=false` remains the ops pin — issue **#102** still open until RSS soak proves stable. |

## Morning verify (post-#107)

- Bot up, `RestartCount=0`, image on `e26a32d`, RSS ~275 MiB / 1.25 GiB
- Discovery still **false**; Redis AUTH + loopback OK
- Equities intact after redeploy (no wipe / no soft-admit restore)

## Post-09:00 follow-up (~09:25 WEST)

- **SEC window:** worker had slept from a pre-04:00 ET check; one restart put it in-window. Full equity cycle cached `sec:integrity:{ELV,GOOG,GOOGL,MPC,UNH,VLO}` (6/6), then sleep 3600s. Gemini LLM debate returns 403 (blocked key) but scores still land (fallback 50).
- **Live sanity:** discovery still `false`; Active = 3 equities + 4 crypto (all `is_cointegrated=true`); clean `docker diff`; Redis `127.0.0.1:6379` + AUTH PONG; bot RSS ~277 MiB / 1.25 GiB.
- **Equity knobs:** still `COINTEGRATION_ROLLING_PASS_RATE=0.40`, `MAX_ACTIVE_PAIRS=30`; rollback backup `~/.env.trading.bak_equity_20260804_080557`; tracked in **#109** (#110 closed as duplicate).
- **Discovery soak:** longer note on **#102** — keep OFF through US open.

## Residual risks (do not ignore)

1. **Public ports** — confirm dashboard/API/gRPC stay loopback or Tailscale-only; re-run security probe after recreates.
2. **Unmanaged positions** — broker RISK ALERT noise; paper continues via `IGNORE_UNMANAGED_POSITIONS=true` (informational, not auto-flatten).
3. **RSS soak** — keep discovery OFF until RSS stays comfortably under ~700 MiB for 2–3h on the prune-valve image (**#102**).
4. **SEC LLM** — EDGAR path works; Gemini debate is 403-blocked (scores use fallback). Fix/rotate key when convenient — not blocking integrity cache.

## Do not flip yet

- Discovery / auto-promote
- Real-money live / auth weaken
- Soft-admit back into Active
