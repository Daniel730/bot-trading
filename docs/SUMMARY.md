# SUMMARY.md

## What shipped (2026-08-04)

1. Full-day SHADOW soak + Phase-1…4 platform hardening.
2. **Phase-5 ops foundations** — provenance, replay CLI, shadow/LIVE divergence, rollback script, limited-LIVE kill criteria (`docs/AUDIT_PHASE5_OPS.md`).

## Verdict

**READY FOR LIMITED LIVE CAPITAL** (place money) — not yet *trust large capital*.

### Scale-up conditions
- 48h soak without invariant violations
- Small acceptable-loss capital
- Objective kills: reconcile fails, divergences, drawdown
- Continuous monitoring + `scripts/rollback_deploy.sh`
- Strategy OOS / multi-regime evidence before increasing size

## Phase-5 tools

```bash
PYTHONPATH=/workspace .venv/bin/python scripts/replay_trade.py --signal-id <uuid>
bash scripts/rollback_deploy.sh <previous-sha>
PYTHONPATH=/workspace .venv/bin/python scripts/phase4_soak_chaos.py --signals 100000 --hours 48
```

## Scores (platform Phase-4)

| Security | Reliability | Trading Safety | Recoverability |
|---|---|---|---|
| 8.2 | 8.5 | 8.6 | 8.4 |

Observability (Phase-5 ops): **7.8** — reconstruction path exists; dual shadow executor still skeletal.

## PR

https://github.com/Daniel730/bot-trading/pull/117
