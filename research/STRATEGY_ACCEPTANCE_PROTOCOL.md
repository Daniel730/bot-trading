# Strategy Acceptance Protocol

A strategy may not enter LIVE (including limited live) until a research report JSON passes this protocol.

## Statistical floors (defaults)

| Metric | Minimum / Maximum |
|---|---|
| Sharpe | ≥ 1.0 |
| Sortino | ≥ 1.2 |
| Profit Factor | ≥ 1.3 |
| Max Drawdown | ≤ 20% |
| Expectancy | > 0 |
| Trade count | ≥ 50 |

## Robustness

Shock every tuned parameter by **±10%**. Worst-case Sharpe drop vs baseline must be ≤ 35% relative.

If small shocks destroy performance → treat as overfit → **reject**.

## Costs (always on)

Simulations must include at least:

- spread
- slippage
- commission

Warnings if latency / partial fills are omitted; prefer modeling them before scale-up.

## Walk-forward discipline

1. Train  
2. Validate  
3. **Freeze** parameters  
4. Run next period  
5. Never refit looking at the future (`parameters_refit_on_test: false`)

## Out-of-sample

Holdout (or purged CV) completed and reported separately from training metrics.

## Selection bias

If `combinations_tested` is large, require `multiple_testing_corrected: true` or the checker rejects.

## CLI

```bash
PYTHONPATH=/workspace .venv/bin/python scripts/check_strategy_acceptance.py \
  --report research/examples/sample_strategy_report.json
```

Exit code `0` = accepted; `2` = rejected.
