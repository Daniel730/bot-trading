# SUMMARY.md

## Status

**READY FOR LIMITED LIVE CAPITAL** (place money) — not yet trust large capital.

Dominant risk shifted from engineering → **quantitative research quality**.

## Dual track

| Track | Mode | Effort |
|---|---|---|
| Platform | Maintenance / hardening | ~10% |
| Quant research | Primary | ~60% + 20% observability |

See `docs/ROADMAP_DUAL_TRACK.md`, `research/`.

## Recent foundations

- Decision Package `decision_package/v1` (`scripts/replay_trade.py --decision-package`)
- Divergence **severity** (INFO/WARNING/CRITICAL/FATAL) — no kill on INFO piles
- Strategy Acceptance Protocol checker (`scripts/check_strategy_acceptance.py`)

## Scale-up conditions

1. 48h soak clean  
2. Small capital  
3. Severity-based stops + rollback  
4. Strategy report **accepted** under the protocol (OOS, costs, robustness, no lookahead)

## PR

https://github.com/Daniel730/bot-trading/pull/117
