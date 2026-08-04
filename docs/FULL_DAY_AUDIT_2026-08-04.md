# Full-day local application audit — 2026-08-04

Continuation after the overnight bot-server audit (`docs/OVERNIGHT_2026-08-04.md`).
This run validates **latest `master`** (`109b8bb` + this branch) locally so findings
do not depend on production hotpatches.

## Mode under test

| Knob | Value | Why |
|---|---|---|
| Code | `origin/master` @ `109b8bb` + shadow eligibility fix | Latest overnight merges |
| `PAPER_TRADING` | `true` (SHADOW) | Injected Alpaca keys return **unauthorized** — broker paper cannot boot |
| `LIVE_CAPITAL_DANGER` | `false` | Required with shadow |
| `PAIR_DISCOVERY_ENABLED` | `false` | Matches ops pin #102 |
| `COINTEGRATION_ROLLING_PASS_RATE` | `0.40` | Matches overnight equity admit knobs #109 |
| `MAX_ACTIVE_PAIRS` | `30` | Same |
| Market data | yfinance fallback (no Polygon / Alpaca bars) | Unauthorized Alpaca |

## Findings so far

### F1 — Shadow paper emptied by brokerage asset gate (FIXED)

Unauthorized / placeholder Alpaca keys make `_get_active_symbols()` return `{}`, so
`evaluate_pair` rejected every leg with `asset_not_active_in_brokerage:*` and the
monitor initialized **0/0 pairs**. This contradicts AGENTS.md paper-mode guidance
(placeholders are non-fatal; shadow fills).

**Fix:** skip the Spec 045 broker asset check when `PAPER_TRADING=true`
(`require_broker_active` defaults to `not settings.PAPER_TRADING`). Broker-paper and
live remain fail-closed. Covered by unit tests.

### F2 — Injected Alpaca API credentials are unauthorized (OPS)

`alpaca_trade_api` against `https://paper-api.alpaca.markets` returns `unauthorized`
for the Cursor-injected `ALPACA_API_KEY` / `ALPACA_API_SECRET`. Broker-paper soak is
blocked until keys are rotated. Shadow soak continues.

### F3 — Overnight equity roster fails rolling cointegration on yfinance @ 0.40

With the same `COINTEGRATION_ROLLING_PASS_RATE=0.40` used on bot-server:

| Pair | Local pass_rate | Result |
|---|---|---|
| GOOGL/GOOG | 0.32 (31 windows) | Benched |
| UNH/ELV | 0.32 | Benched |
| VLO/MPC | 0.32 | Benched |

So the temporary 0.40 knob (#109) is **borderline and data-source sensitive**.
Alpaca daily bars on bot-server may pass where yfinance fails. Do not treat 0.40 as
stable without broker-bar soak evidence.

### F4 — Healthy crypto scan loop (working)

After F1 fix: health checks passed, discovery stayed OFF, continuous scan started
with **5 Active crypto pairs** (BTC/ETH, ETH/SOL, AVAX/DOT, AVAX/LTC, XRP/XLM).
First iterations: all `below_entry_threshold`, no crashes.

### F5 — Dashboard cash poll still hits Alpaca in shadow (FIXED)

Even in SHADOW mode the dashboard periodically tried `get_account_cash` and logged
`Alpaca failed to fetch account cash: unauthorized`. Fixed: metric polls use
`PAPER_TRADING_STARTING_CASH` when `PAPER_TRADING=true`.

### F6 — Live Kalman beta can exceed admission hedge cap (FIXED)

`PAIR_DISCOVERY_MAX_ABS_HEDGE=25` is enforced on OLS hedge at warm-up, but the
Kalman filter can drift past it while staying under the hard clip (0.001–1000).
Observed on this soak:

| Pair | Init OLS hedge | Live Kalman beta |
|---|---|---|
| BTC-USD/ETH-USD | ~12.6 | ~34.1 |
| ETH-USD/SOL-USD | ~-8.9 | ~25.2 |

**Fix:** `process_pair` now skips with `extreme_kalman_beta` when
`abs(kalman_beta) > PAIR_DISCOVERY_MAX_ABS_HEDGE` (same helper as admission).

### F7 — Near-zero OLS hedge still admits (WATCH)

`AVAX-USD/LTC-USD` warmed with OLS hedge ≈ `-0.002` (passes `is_hedge_ratio_sane`
because only exact `0.0` is rejected) and scans at Kalman beta ≈ `0.12`. Sizing
with near-zero hedge is fragile. **Mitigation:** admission paths now enforce
`PAIR_DISCOVERY_MIN_ABS_HEDGE` (default `0.05`) via `is_hedge_ratio_sane(...,
min_abs_hedge=...)`. Live Kalman scans do not apply the floor.

## Soak harness

- Monitor: tmux `audit-monitor` → `data/audit/logs/monitor.out`
- Sampler: tmux `audit-sampler` → `data/audit/samples/soak_YYYYMMDD.jsonl`
  (auth via `X-Dashboard-Session`)
- Frontend: tmux `audit-frontend` → `:5173`

Sampler authenticates with dashboard token + TOTP (`data/audit/`).

## Residual watch list (in progress)

1. RSS / prune valve over multi-hour window (#102 evidence)
2. Signal → orchestrator → shadow fill path when |z| ≥ entry (and beta sane)
3. Equity re-admit behavior once US cash session is open (still yfinance-only here)
4. Optional min-abs hedge floor (F7) — **done** (`PAIR_DISCOVERY_MIN_ABS_HEDGE=0.05`)
5. Rotate Alpaca keys and re-run broker-paper soak
