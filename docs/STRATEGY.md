# Strategy And Risk Logic

The strategy is pairs trading with multiple layers of economic, statistical, and operational filtering. The bot is built to prefer fewer, explainable signals over broad brute-force scanning.

## Pair Admission

Candidate pairs are first filtered by `src/services/pair_eligibility_service.py`.

A pair can be rejected before any Kalman state is allocated when:

- it mixes crypto and equity tickers;
- the two tickers trade in different sessions;
- the pair crosses settlement currencies while cross-currency blocking is enabled;
- an LSE ticker is present while short-hold LSE pairs are blocked;
- estimated round-trip cost exceeds `PAIR_MAX_ROUND_TRIP_COST_PCT`.

Crypto pairs are admitted as 24/7 same-session pairs and use the Web3/active-broker venue dispatcher rules later.

## Cointegration

The monitor uses historical prices to check cointegration before activating a pair:

- Static Engle-Granger/ADF logic in `arbitrage_service`.
- Optional rolling-window stability with `COINTEGRATION_ROLLING_ENABLED`.
- Daily re-checks can suspend a pair when cointegration breaks and reactivate it when restored.

Rolling settings:

| Setting | Meaning |
|---|---|
| `COINTEGRATION_ROLLING_WINDOW` | Window size used for stability checks |
| `COINTEGRATION_ROLLING_STEP` | Rolling stride |
| `COINTEGRATION_ROLLING_PASS_RATE` | Minimum passing-window rate |

## Kalman Spread Model

For each active pair, a Kalman filter estimates the dynamic relationship:

```text
spread = price_a - (alpha + beta * price_b)
```

Signals use the z-score computed from the prior state before the current tick is absorbed. This avoids treating the new observation as already mean-reverted.

Session-boundary handling:

- `KALMAN_USE_Q_INFLATION=true` inflates process noise for the first bars after an equity session opens.
- If disabled, the monitor can fall back to a covariance uncertainty bump.

## Entry Gate

Base entry threshold:

```text
abs(z_score) > MONITOR_ENTRY_ZSCORE
```

Optional cost scaling:

```text
entry_threshold = MONITOR_ENTRY_ZSCORE * min(pair_cost / baseline, cap)
```

controlled by:

- `MONITOR_ENTRY_ZSCORE_COST_SCALING_ENABLED`
- `MONITOR_ENTRY_ZSCORE_COST_BASELINE`
- `MONITOR_ENTRY_ZSCORE_COST_SCALING_CAP`

## Orchestrator Validation

The orchestrator is an async Python ensemble, not a required LangGraph runtime path. It validates a z-score signal with:

1. `DEGRADED_MODE` circuit-breaker check.
2. Macro beacon fail-fast veto by sector.
3. Bull and bear agent evaluation.
4. Cached SEC/fundamental integrity scores from Redis.
5. Whale watcher context for crypto-sensitive flows.
6. Portfolio manager confidence adjustment.
7. Historical global accuracy multiplier.
8. Per-ticker beacon flash-crash veto.

Hard veto examples:

- sector beacon is in `EXTREME_VOLATILITY`;
- fundamental score is below `ORCH_FUNDAMENTAL_VETO_SCORE`;
- whale watcher returns a veto;
- operational status is `DEGRADED_MODE`.

## Risk Guards

| Guard | Purpose |
|---|---|
| Spread guard | Rejects trades when combined bid/ask spread exceeds `SPREAD_GUARD_MAX_PCT`. |
| Cluster guard | Prevents projected sector exposure above `MAX_SECTOR_EXPOSURE`. |
| Friction guard | Rejects trades whose estimated fee/spread friction exceeds venue thresholds. |
| Budget guard | Caps spend by venue using the active equity broker budget path and `WEB3_BUDGET_USD`. |
| Live sell preflight | Blocks Trading 212 sell legs when available shares are insufficient. |
| Atomic leg guard | Aborts after leg A failure; emergency-closes leg A when leg B fails. |
| Kill switch | Closes positions when current value breaches `FINANCIAL_KILL_SWITCH_PCT`. |
| Statistical exits | Take profit at `TAKE_PROFIT_ZSCORE`; stop loss at `STOP_LOSS_ZSCORE`. |

## Execution Direction

When z-score is positive:

```text
Short A / Long B
```

When z-score is negative:

```text
Long A / Short B
```

In paper mode the shadow service records simulated fills. In live mode the Python brokerage dispatcher routes:

- equity/non-crypto tickers to the configured broker provider (`BROKERAGE_PROVIDER=T212|ALPACA`);
- `*-USD` crypto tickers to Web3 when Web3 is enabled and paper mode is off.

## Position Exit

Open positions are evaluated each loop:

- financial kill switch first;
- then Kalman-based take profit or stop loss;
- paper exits also call `shadow_service.close_simulated_trade()` for shadow ledger consistency;
- realized P&L is directional per leg.
