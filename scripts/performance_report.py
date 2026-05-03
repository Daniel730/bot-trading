#!/usr/bin/env python3
"""Generate weekly KPI summary from CSV logs.

Usage:
  python scripts/performance_report.py --metrics-dir data/metrics
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class KPI:
    net_return_pct: float
    max_drawdown_pct: float
    current_drawdown_pct: float
    recovery_days: int | None
    trades: int
    fees_total: float


def _read_equity(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date_utc" not in df.columns or "equity" not in df.columns:
        raise ValueError("equity_daily.csv must include date_utc and equity")
    for col in ("deposits", "withdrawals"):
        if col not in df.columns:
            df[col] = 0.0
    df["date_utc"] = pd.to_datetime(df["date_utc"], utc=True)
    return df.sort_values("date_utc").reset_index(drop=True)


def _read_fills(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"timestamp_utc", "fee"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"orders_fills.csv missing columns: {sorted(missing)}")
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    return df


def _drawdown_stats(equity: pd.Series, dates: pd.Series) -> tuple[float, float, int | None]:
    peaks = equity.cummax()
    drawdowns = (peaks - equity) / peaks
    max_dd = float(drawdowns.max() * 100)
    current_dd = float(drawdowns.iloc[-1] * 100)

    max_idx = int(drawdowns.idxmax())
    if drawdowns.iloc[max_idx] <= 0:
        return max_dd, current_dd, 0

    peak_val = peaks.iloc[max_idx]
    trough_date = dates.iloc[max_idx]
    post = equity.iloc[max_idx + 1 :]
    recovered = post[post >= peak_val]
    if recovered.empty:
        recovery_days = None
    else:
        recovery_date = dates.loc[recovered.index[0]]
        recovery_days = int((recovery_date - trough_date).days)
    return max_dd, current_dd, recovery_days


def compute_kpis(equity_df: pd.DataFrame, fills_df: pd.DataFrame) -> KPI:
    start = equity_df.iloc[0]
    end = equity_df.iloc[-1]

    start_equity = float(start["equity"])
    end_equity = float(end["equity"])
    deposits = float(equity_df["deposits"].sum())
    withdrawals = float(equity_df["withdrawals"].sum())

    net_return_pct = ((end_equity - start_equity - deposits + withdrawals) / start_equity) * 100

    max_dd, current_dd, recovery_days = _drawdown_stats(equity_df["equity"], equity_df["date_utc"])

    return KPI(
        net_return_pct=float(net_return_pct),
        max_drawdown_pct=max_dd,
        current_drawdown_pct=current_dd,
        recovery_days=recovery_days,
        trades=len(fills_df),
        fees_total=float(fills_df["fee"].sum()),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics-dir", default="data/metrics")
    args = parser.parse_args()

    metrics_dir = Path(args.metrics_dir)
    equity_df = _read_equity(metrics_dir / "equity_daily.csv")
    fills_df = _read_fills(metrics_dir / "orders_fills.csv")

    kpi = compute_kpis(equity_df, fills_df)

    print("=== KPI SUMMARY ===")
    print(f"Net return (%): {kpi.net_return_pct:.2f}")
    print(f"Max drawdown (%): {kpi.max_drawdown_pct:.2f}")
    print(f"Current drawdown (%): {kpi.current_drawdown_pct:.2f}")
    print(f"Recovery (days): {kpi.recovery_days if kpi.recovery_days is not None else 'not yet recovered'}")
    print(f"Trades: {kpi.trades}")
    print(f"Fees total: {kpi.fees_total:.4f}")


if __name__ == "__main__":
    main()