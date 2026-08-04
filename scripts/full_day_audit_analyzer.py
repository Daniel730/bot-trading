#!/usr/bin/env python3
"""Periodic soak analyzer — summarizes monitor health for the full-day audit."""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONITOR_LOG = ROOT / "data" / "audit" / "logs" / "monitor.out"
SAMPLES = ROOT / "data" / "audit" / "samples"
OUT = ROOT / "data" / "audit" / "soak_summary.json"
INTERVAL = 300  # 5 minutes


def _strip(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def analyze() -> dict:
    text = MONITOR_LOG.read_text(encoding="utf-8", errors="replace") if MONITOR_LOG.exists() else ""
    lines = [_strip(l) for l in text.splitlines()]
    reasons = Counter()
    for line in lines:
        m = re.search(r"PAIR SKIP \[([^\]]+)\]: (\S+)", line)
        if m:
            reasons[m.group(2)] += 1
        m = re.search(r"Iteration Complete \| Scanned: (\d+)/(\d+) \| Signals: (\d+) \| Vetoed: (\d+) \| Open: (\d+)", line)
    iterations = len([l for l in lines if "Iteration Complete" in l])
    errors = len([l for l in lines if re.search(r"\bERROR\b|Traceback", l)])
    unauthorized = len([l for l in lines if "unauthorized" in l.lower()])
    signals = len([l for l in lines if "SIGNAL [" in l])
    executed = len([l for l in lines if "EXECUTE" in l or "OPEN_PAIR" in l or "shadow" in l.lower() and "fill" in l.lower()])

    rss_series = []
    sample_path = SAMPLES / f"soak_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
    if sample_path.exists():
        for raw in sample_path.read_text(encoding="utf-8").splitlines()[-200:]:
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            mon = row.get("monitor") or {}
            if mon.get("rss_mb") is not None:
                rss_series.append(mon["rss_mb"])

    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "monitor_log_lines": len(lines),
        "iterations": iterations,
        "errors": errors,
        "unauthorized": unauthorized,
        "signals": signals,
        "executed_like": executed,
        "skip_reasons": reasons.most_common(20),
        "rss_mb": {
            "n": len(rss_series),
            "last": rss_series[-1] if rss_series else None,
            "min": min(rss_series) if rss_series else None,
            "max": max(rss_series) if rss_series else None,
        },
    }
    OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    while True:
        try:
            analyze()
        except Exception as exc:  # noqa: BLE001
            print(f"analyze_failed: {exc}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
