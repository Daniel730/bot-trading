# Strategy And Risk Logic

The strategy is pairs trading with multiple layers of economic, statistical, and operational filtering. The bot is built to prefer fewer, explainable signals over broad brute-force scanning.

## Pair Admission

The default equity universe is a **curated US liquid list** in `settings.ARBITRAGE_PAIRS`
(same-session, Alpaca-friendly). Regional EU/LSE/Xetra/cross-listed pairs were removed from
defaults to cut rate-limit noise and friction; re-add deliberately via dashboard overrides if
needed. Automatic pair discovery is frozen by default (`PAIR_DISCOVERY_ENABLED=false`,
`PAIR_DISCOVERY_AUTO_PROMOTE=false`); operators can still run one-shot discover from the dashboard.

Candidate pairs are first filtered by `src/services/pair_eligibility_service.py`.

A pair can be rejected before any Kalman state is allocated when:

- it mixes crypto and equity tickers;
- the two tickers trade in different sessions;
- the pair crosses settlement currencies while cross-currency blocking is enabled;
- an LSE ticker is present while short-hold LSE pairs are blocked;
- estimated round-trip cost exceeds `PAIR_MAX_ROUND_TRIP_COST_PCT`.
- a single-bar absolute return exceeds `CORP_ACTION_PRICE_JUMP_PCT` (default 15%) — the pair is
  benched and Kalman state is invalidated (split / symbol-change / bad stitch protection).

Crypto pairs are admitted as 24/7 same-session pairs and use the active Alpaca brokerage path later. Web3 execution is legacy/disabled in the current runtime.

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
entry_threshold = MONITOR_ENTRY_ZSCORE * (
  1 + (cap - 1) * clamp((pair_cost - baseline) / (PAIR_MAX_ROUND_TRIP_COST_PCT - baseline), 0, 1)
)
```

controlled by:

- `MONITOR_ENTRY_ZSCORE_COST_SCALING_ENABLED`
- `MONITOR_ENTRY_ZSCORE_COST_BASELINE`
- `MONITOR_ENTRY_ZSCORE_COST_SCALING_CAP`
- `PAIR_MAX_ROUND_TRIP_COST_PCT`

## Orchestrator Validation

The orchestrator is an async Python ensemble, not a required LangGraph runtime path. It validates a z-score signal with:

1. `DEGRADED_MODE` circuit-breaker check.
2. Macro beacon fail-fast veto by sector.
3. Bull and bear agent evaluation. Default path is a labeled z-score heuristic (`source=heuristic_stub`), not LLM theater (legacy fixed 0.7/0.4 removed). Optional Gemini/OpenAI theme scoring requires `BULL_BEAR_LLM_ENABLED=true`, usable keys, and remaining hourly/daily caps; otherwise agents stay heuristic. Orchestrator telemetry uses `HEURISTIC` (not AI BULLISH/BEARISH) for non-LLM payloads and annotates `final_verdict` with a `THEME:` quality note.
4. Cached SEC/fundamental integrity scores from Redis.
5. News risk overlay (opt-in via `NEWS_RISK_ENABLED`, default **false**). Veto-only: material headlines mapped to either leg can hard-veto or shrink confidence. Missing feed/API key → inactive **no-veto** (does not block the book). This is a risk overlay, not directional news alpha.
6. Whale watcher status for crypto-sensitive flows. The hot-path implementation is a hard-dormant stub that reports `INACTIVE` (`active=False`). `WHALE_WATCHER_ENABLED` and related knobs are reserved; flipping the flag alone does not enable flow analysis. Cache-backed logic was removed with the `legacy/` tree (GitHub #91).
7. Portfolio manager confidence adjustment.
8. Historical global accuracy multiplier.
9. Per-ticker beacon flash-crash veto.

Hard veto examples:

- sector beacon is in `EXTREME_VOLATILITY`;
- fundamental score is below `ORCH_FUNDAMENTAL_VETO_SCORE`;
- an **active** news risk agent returns a veto (`NEWS_RISK_ENABLED=true`, feed healthy, materiality ≥ `NEWS_RISK_VETO_SCORE`, ticker-relevant, within TTL);
- an **active** whale watcher returns a veto (`active=True`). The current stub is inactive, so no whale-flow veto or confidence boost/penalty is applied; orchestrator ignores inactive payloads even if they carry veto/multiplier fields;
- operational status is `DEGRADED_MODE`.

Multi-armed bandit weights cover bull, bear, and SEC agents only — whale and news risk are not MAB arms and do not consume Thompson-sampling weight.

## Risk Guards

| Guard | Purpose |
|---|---|
| Spread guard | Rejects trades when combined bid/ask spread exceeds `SPREAD_GUARD_MAX_PCT`. |
| Cluster guard | Prevents projected sector exposure above `MAX_SECTOR_EXPOSURE`. |
| Friction guard | Rejects trades whose estimated fee/spread friction exceeds venue thresholds. |
| Budget guard | Caps spend by venue using the active Alpaca broker budget path. |
| Live sell preflight | Blocks sell legs when available shares are insufficient. |
| Atomic leg guard | Aborts after leg A failure; emergency-closes leg A when leg B fails. |
| Kill switch | Closes positions when current value breaches `FINANCIAL_KILL_SWITCH_PCT`. |
| Corporate-action jump | Benches pair + clears Kalman when a single-bar move exceeds `CORP_ACTION_PRICE_JUMP_PCT`. |
| Statistical exits | Take profit at `TAKE_PROFIT_ZSCORE` (friction hold until fees clear, or force exit at `TAKE_PROFIT_FORCE_EXIT_ZSCORE`); stop loss at `STOP_LOSS_ZSCORE`. |

## Sizing And Realized P&L Honesty

- Position sizing can derive Kelly win probability / payoff from **closed ledger PnLs** via
  `persistence_service.get_kelly_inputs_from_ledger()` once `KELLY_LEDGER_MIN_TRADES` (default 20)
  closed signals exist; below that floor it keeps `DEFAULT_WIN_PROBABILITY` /
  `DEFAULT_WIN_LOSS_RATIO` (never invents a high win rate from a tiny sample).
- Alpaca US equities are commission-free: `FLAT_ORDER_FRICTION_USD` defaults to **0.0** so friction
  gates use bid/ask spread estimates rather than a T212-era flat proxy.
- Shadow fills apply `SHADOW_FILL_SLIPPAGE_BPS` (default 5) adverse mid offset so paper PnL does not
  overstate liquid equity fills.
- `calculate_realized_pnl(..., include_costs=True)` nets entry fees, estimated exit friction, and
  recorded slippage bps when present on the leg / metadata.

## Execution Direction

When z-score is positive:

```text
Short A / Long B
```

When z-score is negative:

```text
Long A / Short B
```

In paper mode the shadow service records simulated fills. Broker Alpaca paper (`PAPER_TRADING=false` + paper-api URL) and real-money live both use Python `BrokerageService` → Alpaca:

- `BROKERAGE_PROVIDER=ALPACA` is required;
- Trading 212 and Web3 execution routes are legacy/disabled and unsupported provider values fail startup;
- Approvals: shadow + Alpaca paper auto-approve via `settings.should_auto_approve_trades`; real-money live always requires human Telegram/dashboard approval (`ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM` is not honored for real capital).
## Position Exit

Open positions are evaluated each loop:

- financial kill switch first;
- then Kalman-based take profit or stop loss;
- paper / shadow exits also call `shadow_service.close_simulated_trade()` for directional PnL logging only; durable close is a single `persistence.close_trade` write (broker paper / live closes skip the shadow log and use broker fill confirmation first);
- close routing follows ledger `execution_lane` / `is_shadow` from open, not only the current `PAPER_TRADING` flag;
- realized P&L is directional per leg.
