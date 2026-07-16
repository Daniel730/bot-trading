#!/usr/bin/env python3
"""Export a Decision Flight Recorder incident pack for Cursor/Hermes.

Examples:
  PYTHONPATH=. python scripts/export_incident_pack.py --last-anomaly
  PYTHONPATH=. python scripts/export_incident_pack.py --signal-id <uuid>
  PYTHONPATH=. python scripts/export_incident_pack.py --scan-id scan-abc123

Note: the ring buffer lives in the running monitor process. This script exports
from the in-process singleton when imported in the same process, or from a
demo/synthetic trail when run standalone (useful for validating pack layout).
For a live bot, prefer calling decision_recorder.export_pack(...) from a
dashboard/admin hook, or attach via the same Python process.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _seed_demo_trail(recorder) -> None:
    """Populate a tiny trail so standalone CLI still produces a readable pack."""
    if recorder.events():
        return
    scan_id = recorder.begin_scan("scan-demo-export")
    recorder.set_pair_id("BTC-USD_ETH-USD")
    recorder.record(
        stage="scan",
        outcome="continue",
        reason="scan_started",
        inputs={"pairs": 2},
        scan_id=scan_id,
    )
    recorder.record(
        stage="pre_signal",
        outcome="skip",
        reason="missing_price",
        inputs={"ticker": "BTC-USD"},
    )
    recorder.set_signal_id("00000000-0000-4000-8000-000000000001")
    recorder.record(
        stage="orchestrator",
        outcome="veto",
        reason="orchestrator_veto",
        inputs={"confidence": 0.12},
    )
    recorder.record(
        stage="process_pair",
        outcome="anomaly",
        reason="exception",
        inputs={"error_type": "RuntimeError", "api_key": "should-redact"},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Decision Flight Recorder incident pack")
    parser.add_argument("--signal-id", default=None, help="Filter by signal_id")
    parser.add_argument("--scan-id", default=None, help="Filter by scan_id")
    parser.add_argument("--pair-id", default=None, help="Filter by pair_id")
    parser.add_argument(
        "--last-anomaly",
        action="store_true",
        help="Export window around the most recent anomaly/promoted event",
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "data" / "incident_packs"),
        help="Output directory for packs (default: data/incident_packs)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Seed a demo trail when the in-memory buffer is empty (standalone CLI)",
    )
    args = parser.parse_args(argv)

    if not (args.signal_id or args.scan_id or args.pair_id or args.last_anomaly):
        args.last_anomaly = True
        args.demo = True

    from src.services.decision_trace_service import decision_recorder

    if args.demo or not decision_recorder.events():
        _seed_demo_trail(decision_recorder)

    journal_refs = {
        "note": "Join existing journals by signal_id; do not duplicate here.",
        "agent_reasoning_trace_id": args.signal_id,
        "trade_journal_signal_id": args.signal_id,
    }
    pack_dir = decision_recorder.export_pack(
        out_dir=args.out_dir,
        signal_id=args.signal_id,
        scan_id=args.scan_id,
        pair_id=args.pair_id,
        last_anomaly=args.last_anomaly,
        journal_refs=journal_refs,
    )
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    print(f"Wrote incident pack: {pack_dir}")
    print(f"Events: {manifest.get('event_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
