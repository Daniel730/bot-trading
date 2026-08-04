#!/usr/bin/env python3
"""Run Strategy Acceptance Protocol against a research report JSON.

Example report keys: see research/examples/sample_strategy_report.json

  PYTHONPATH=/workspace .venv/bin/python scripts/check_strategy_acceptance.py \\
      --report research/examples/sample_strategy_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Strategy Acceptance Protocol checker")
    p.add_argument("--report", required=True, help="Path to research report JSON")
    p.add_argument("--out", default=None, help="Write acceptance result JSON")
    args = p.parse_args(argv)

    from src.services.strategy_acceptance import evaluate_strategy_report_file

    result = evaluate_strategy_report_file(args.report)
    payload = result.to_dict()
    text = json.dumps(payload, indent=2)
    if args.out:
        Path(args.out).write_text(text)
        print(f"Wrote {args.out}")
    else:
        print(text)
    if result.accepted:
        print("ACCEPTED — eligible for paper → limited live pipeline", file=sys.stderr)
        return 0
    print("REJECTED — failures:", file=sys.stderr)
    for f in result.failures:
        print(f"  - {f}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
