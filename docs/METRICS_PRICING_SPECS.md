# Metrics & Pricing Data Spec (30-day bootstrap)

This document defines the minimum analytics required to estimate:

- Monthly net return (%)
- Typical capital size (P50 / P80)
- Max drawdown (%) and recovery time
- Strategy half-life (edge decay)

It is designed to be lightweight and compatible with CSV exports.

## 1) Required logs

## 1.1 `data/metrics/orders_fills.csv`

One row per fill (not per signal).

Columns:

- `timestamp_utc` (ISO-8601, required)
- `symbol` (required)
- `side` (`BUY`/`SELL`, required)
- `qty` (float, required)
- `price` (float, required)
- `fee` (float, required, quote currency)
- `exchange` (string, required)
- `strategy_id` (string, required)
- `latency_ms` (int, optional)
- `order_id` (string, optional)

## 1.2 `data/metrics/equity_daily.csv`

One row per UTC day at a fixed snapshot time.

Columns:

- `date_utc` (`YYYY-MM-DD`, required)
- `equity` (float, required)
- `cash` (float, optional)
- `realized_pnl` (float, optional)
- `unrealized_pnl` (float, optional)
- `fees_total` (float, optional)
- `deposits` (float, optional; default 0)
- `withdrawals` (float, optional; default 0)

## 1.3 `data/metrics/signals.csv` (optional)

Useful for conversion diagnostics (signal quality vs execution quality).

Columns:

- `timestamp_utc`
- `strategy_id`
- `symbol`
- `signal_type`
- `confidence`
- `intended_entry`
- `intended_exit`
- `executed` (`true`/`false`)

## 2) KPI formulas

## 2.1 Monthly net return (%)

For a given month:

`net_return_pct = ((ending_equity - starting_equity - deposits + withdrawals) / starting_equity) * 100`

Notes:

- Use **actual daily equity** snapshots.
- Ensure fees/slippage are reflected in fill and/or equity accounting.

## 2.2 Max drawdown (%)

Given ordered equity series `E_t`:

- `peak_t = max(E_0 ... E_t)`
- `drawdown_t = (peak_t - E_t) / peak_t`
- `max_drawdown_pct = max(drawdown_t) * 100`

Recovery time (days): number of calendar days from drawdown start to first day equity exceeds prior peak.

## 2.3 Typical capital size (P50/P80)

Input source options:

1. Real user-reported allocated capital buckets (preferred)
2. Internal scenarios until user data exists (e.g., 5k / 25k / 100k)

Compute:

- `P50` = median allocated capital
- `P80` = 80th percentile allocated capital

## 2.4 Strategy half-life (practical proxy)

Choose a core edge metric (recommended: expectancy per trade):

`expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss`

Compute rolling windows (weekly or biweekly). Define baseline from first stable window.

Half-life estimate: first window where metric falls to ~50% of baseline for at least 2 consecutive windows.

## 3) Weekly reporting cadence

Run report weekly with:

- Net return MTD and last 7 days
- MDD and current drawdown
- Fees as % of gross pnl
- Slippage estimate as % of gross pnl (if available)
- Trades/day and expectancy/trade
- By symbol and by strategy breakdown

## 4) Pricing translation rule (early-stage)

After 4 weeks live data:

1. Estimate median user monthly net € profit at target capital (P50).
2. Target value capture in the 10–25% range.
3. Start with fixed subscription; add performance-based components only after trust/compliance review.

## 5) Implementation notes

- Keep timestamps in UTC only.
- Do not mix backtest and live data in the same KPI output.
- Freeze strategy logic during measurement windows unless critical bugs occur.