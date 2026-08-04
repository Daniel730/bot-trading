# Research Track — Reproducible Pipeline

Platform work is in **maintenance mode**. This directory owns **quantitative research**.

## Pipeline (nothing skips a stage)

```
Market Data
    → Feature Generation
    → Walk-forward split
    → Training
    → Validation
    → Out-of-sample
    → Paper
    → Limited Live
    → Scale Capital
```

Gate between stages: **Strategy Acceptance Protocol**  
(`src/services/strategy_acceptance.py`, `scripts/check_strategy_acceptance.py`).

## Selection bias

Exploring many indicators × timeframes × filters × parameters creates false winners by chance.

Mandatory disclosures in every report:

- `search_space.combinations_tested`
- `search_space.multiple_testing_corrected`
- frozen parameters after validation (no refit on test)

## Effort allocation (guidance)

| Track | Share | Focus |
|---|---|---|
| Quant research & statistical validation | ~60% | Edge, OOS, regimes, costs |
| Observability / post-trade analysis | ~20% | Decision packages, replay |
| Operations | ~10% | Deploy, alerts, soak |
| Platform maintenance | ~10% | Broker API, bugs, no big rewrites |

See `docs/ROADMAP_DUAL_TRACK.md` and `research/STRATEGY_ACCEPTANCE_PROTOCOL.md`.
