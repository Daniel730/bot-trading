# Dual-Track Roadmap

After Phases 1–5 the **dominant risk is no longer engineering** — it is **quantitative research quality** (edge, overfitting, costs, regimes).

## Track 1 — Platform (maintenance)

Objectives:

- Keep reliability (exactly-once, broker SoT, distributed locks, LIVE checklist)
- Track broker API changes
- Fix production bugs
- Improve observability incrementally

**Avoid** large architectural refactors without a concrete incident or requirement.

## Track 2 — Quantitative research (~80% of new effort)

Reproducible pipeline; nothing reaches LIVE without every stage:

Market Data → Features → Walk-forward → Train → Validate → OOS → Paper → Limited Live → Scale

Gate: [Strategy Acceptance Protocol](../research/STRATEGY_ACCEPTANCE_PROTOCOL.md).

Suggested effort mix:

| Bucket | % |
|---|---|
| Research & statistical validation | 60 |
| Observability / post-trade tools | 20 |
| Operations | 10 |
| Platform maintenance | 10 |

## Place money vs trust money

| | |
|---|---|
| **READY FOR LIMITED LIVE CAPITAL** | Platform will not silently double-order / bypass halt / invent broker state |
| **Trust larger capital** | Strategy passes acceptance protocol across regimes + costs + robustness; Decision Packages reconstruct *why* |

## Decision Package

Every trade should be explainable via `decision_package/v1` JSON (see `src/services/decision_package.py`):

provenance versions + market snapshot + feature vector + signal + risk checks + broker state + decision + execution result.

```bash
PYTHONPATH=/workspace .venv/bin/python scripts/replay_trade.py --signal-id <uuid> --decision-package
```

## Divergence severity (not raw counts)

| Severity | Action |
|---|---|
| INFO | Log only (e.g. &lt;500ms skew) |
| WARNING | Reconcile attention |
| CRITICAL | Block new entries |
| FATAL | Block + recommend flatten / halt |

INFO/WARNING piles do not kill the bot; one FATAL does.
