# SUMMARY.md

> **Point-in-time readiness verdict.** Re-verify against current code, GitHub issues, and `docs/tofix.md` before treating this as an operational go-ahead.

## Status

**READY FOR LIMITED LIVE CAPITAL** (place money) — not yet trust large capital.

Dominant risk shifted from engineering → **quantitative research quality**.

## Dual track

| Track | Mode | Effort |
|---|---|---|
| Platform | Maintenance / hardening | ~10% |
| Quant research | Primary | ~60% + 20% observability |

See `docs/ROADMAP_DUAL_TRACK.md`, `research/`. Observability **targets** (OTel/Sentry/etc.) are tracked in `docs/AGENT_WORKFLOW.md` / issues #118–#122 — internal telemetry exists; vendor APM does not.

## Recent foundations

- Decision Package `decision_package/v1` (`scripts/replay_trade.py --decision-package`)
- Divergence **severity** (INFO/WARNING/CRITICAL/FATAL) — no kill on INFO piles
- Strategy Acceptance Protocol checker (`scripts/check_strategy_acceptance.py`)
- Agent workflow process + PR/issue templates (`docs/AGENT_WORKFLOW.md`, #136)
- Compose `bot` restart `unless-stopped` (#137 / #138)

## Scale-up conditions

1. 48h soak clean  
2. Small capital  
3. Severity-based stops + rollback  
4. Strategy report **accepted** under the protocol (OOS, costs, robustness, no lookahead)

## Related

- PR snapshot historically: https://github.com/Daniel730/bot-trading/pull/117
- Current docs index: `docs/README.md`