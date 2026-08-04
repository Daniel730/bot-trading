#!/usr/bin/env python3
"""Operator script: audit (and optionally repair) TradeJournal vs CLOSED TradeLedger."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Upsert missing journal exit_reason from ledger metadata (else MANUAL).",
    )
    args = parser.parse_args()

    from src.services.journal_audit_service import audit_journal_vs_ledger

    summary = await audit_journal_vs_ledger(repair=args.repair)
    print(json.dumps(summary, indent=2, default=str))
    return 1 if summary.get("gap_count") and not args.repair else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
