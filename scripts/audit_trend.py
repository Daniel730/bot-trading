#!/usr/bin/env python3
"""Historical trend viewer for the Daily Bot Audit (brief §11).

Reads the machine-readable per-day metrics written by daily_bot_audit.py
(reports/daily-audit/metrics/YYYY-MM-DD.json) and answers the brief's
questions: better/worse than yesterday? are errors/retries/rejections/RAM
rising? which problems are recurring?

Usage:
  python scripts/audit_trend.py [--days N] [--json]

Exit code: 0 if no worsening signal, 1 if any metric worsened vs previous day
or a recurring problem is detected (useful for cron alerting).
"""
from __future__ import annotations

import argparse
import json
import sys

# Import the engine (works when run as a file with ROOT on sys.path, or as a
# package when PYTHONPATH includes the repo root).
try:
    from scripts.daily_bot_audit import compute_historical_trend
except ImportError:  # pragma: no cover - fall back when run directly
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    from scripts.daily_bot_audit import compute_historical_trend


def _render(hist: dict) -> str:
    if not hist.get("available"):
        return f"HISTORICAL TREND: {hist.get('note', 'no data')}"
    lines = [
        f"HISTORICAL TREND ({hist['from']} -> {hist['to']}, "
        f"{hist['metrics_files']} daily metrics)",
        f"  verdict trajectory: {hist['verdict_trajectory']}",
        "  deltas (first -> last):",
    ]
    for k, v in hist.get("deltas", {}).items():
        arrow = "▲" if v["delta"] > 0 else ("▼" if v["delta"] < 0 else "▬")
        lines.append(f"    {arrow} {k}: {v['first']} -> {v['last']} (Δ{v['delta']})")
    if hist.get("worsening_vs_prev"):
        lines.append("  WORSENING vs previous day:")
        for k, w in hist["worsening_vs_prev"].items():
            lines.append(f"    ! {k}: {w['prev']} -> {w['last']} (+{w['delta']})")
    if hist.get("recurring"):
        lines.append("  RECURRING problem signals:")
        for k, r in hist["recurring"].items():
            lines.append(f"    * {k}: hot on {r['days_hot']} days")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Daily Bot Audit historical trend")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true", help="emit raw JSON")
    args = ap.parse_args(argv)

    hist = compute_historical_trend(days=args.days)
    if args.json:
        print(json.dumps(hist, indent=2))
    else:
        print(_render(hist))

    # Alerting exit code: worsening or recurring bad-up metric.
    if hist.get("available"):
        if hist.get("worsening_vs_prev") or hist.get("recurring"):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
