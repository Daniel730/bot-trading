# Quickstart: Paper-Trading Boot Sequence

**After the 036-paper-readiness-blockers feature ships**, this is the complete path from cold machine to a scanning paper-mode bot.

## Prerequisites (one-time)

- Docker Desktop running.
- `.env` populated (copy from `.env.template`; fill in rotated credentials per `rotation-runbook.md`).
- `PAPER_TRADING=true`, `LIVE_CAPITAL_DANGER=false` in `.env`.
- `.venv` with `pip install -r requirements.txt` completed.

## Boot (every run)

```bash
# 1. Infrastructure
docker compose -f docker-compose.backend.yml up -d redis postgres

# 2. Wait for health
docker compose -f docker-compose.backend.yml ps   # both should be "healthy"

# 3. Monitor
source .venv/bin/activate
python src/monitor.py
```

## Expected log sequence

```
INFO - MODE: PAPER | DEV_MODE=false | Pair universe: 21 equity pairs | Next NYSE open: 2026-04-20 09:30 America/New_York
INFO - Initializing Databases...
INFO - Initializing pairs in PROD mode...
INFO - Pair AAPL/MSFT initialized (Coint: True).
... (one line per pair) ...
INFO - Running System Health Checks...
INFO - All Health Checks Passed (Postgres, Redis, T212). Bot is active.
INFO - Circuit breaker reset to NORMAL on startup.
INFO - SCAN [AAPL/MSFT] Current Z-Score: 0.41 | Beta: 1.0023
...
```

When a signal fires (`|z| > 2.0`):

```
INFO - SIGNAL [PEP/KO] z=2.134 beta=0.9871 — running AI validation
INFO - ORCHESTRATOR [PEP/KO] confidence=0.723 verdict=MAB: Bull(0.41), Bear(0.32) | SORTINO OPTIMAL ...
INFO - PAPER TRADING: Executing shadow trade Short-Long for PEP/KO
SHADOW TRADE EXECUTED: Short-Long for PEP_KO at 175.22/64.18
```

And a Telegram message arrives (no Approve/Reject buttons):

```
📝 Paper trade executed
Pair: PEP/KO
Direction: Short-Long
z-score: 2.13
Confidence: 0.72
```

## If the monitor idles silently

- Check `DEV_MODE` — if `false` and weekend/off-hours, it's correctly waiting for NYSE open. The pre-flight line will have said so.
- Check `docker compose logs redis postgres` — both must be reachable.
- Check the Telegram heartbeat — the bot posts "🚀 Arbitrage Bot Online" once health checks pass. If that message never arrives, Telegram credentials are likely wrong.
