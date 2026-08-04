#!/usr/bin/env python3
"""Replay / reconstruct a trade offline for forensic review (Phase-5).

Examples:
  PYTHONPATH=/workspace .venv/bin/python scripts/replay_trade.py --trade-id <uuid>
  PYTHONPATH=/workspace .venv/bin/python scripts/replay_trade.py --signal-id <uuid> --decision-package
  PYTHONPATH=/workspace .venv/bin/python scripts/replay_trade.py --order-id <id> --out /tmp/pack.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def _run(args: argparse.Namespace) -> int:
    from src.services.trade_reconstruction import reconstruct_trade

    try:
        pack = await reconstruct_trade(
            trade_id=args.trade_id,
            signal_id=args.signal_id,
            order_id=args.order_id,
            incident_pack_dir=args.incident_dir,
        )
    except LookupError as exc:
        print(f"NOT FOUND: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.decision_package:
        from src.services.decision_package import (
            decision_package_from_reconstruction,
            write_decision_package,
        )

        dp = pack.get("decision_package") or decision_package_from_reconstruction(pack)
        path = write_decision_package(dp, out_dir=args.decision_dir)
        print(f"Decision package: {path}")
        if args.out:
            Path(args.out).write_text(json.dumps(dp, indent=2, default=str))
            print(f"Wrote {args.out}")
        elif not args.quiet:
            print(json.dumps(dp, indent=2, default=str))
        return 0

    text = json.dumps(pack, indent=2, default=str)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        print(f"Wrote {out}")
    else:
        print(text)

    prov = pack.get("provenance") or {}
    now = pack.get("runtime_provenance_now") or {}
    if prov.get("git_commit") and now.get("git_commit") and prov["git_commit"] != now["git_commit"]:
        print(
            f"NOTE: trade git_commit={prov['git_commit']} != runtime={now['git_commit']}",
            file=sys.stderr,
        )
    if prov.get("config_hash") and now.get("config_hash") and prov["config_hash"] != now["config_hash"]:
        print(
            f"NOTE: trade config_hash={prov['config_hash']} != runtime={now['config_hash']}",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Reconstruct a trade for offline forensic replay")
    p.add_argument("--trade-id", default=None, help="TradeLedger UUID")
    p.add_argument("--signal-id", default=None, help="Signal UUID")
    p.add_argument("--order-id", default=None, help="Broker or client_order_id")
    p.add_argument("--out", default=None, help="Write JSON pack to path")
    p.add_argument(
        "--decision-package",
        action="store_true",
        help="Emit canonical decision_package/v1 (why the trade happened)",
    )
    p.add_argument(
        "--decision-dir",
        default=str(ROOT / "data" / "decision_packages"),
        help="Directory for decision package files",
    )
    p.add_argument("--quiet", action="store_true", help="Less stdout when writing packages")
    p.add_argument(
        "--incident-dir",
        default=str(ROOT / "data" / "incident_packs"),
        help="Directory of exported decision incident packs",
    )
    args = p.parse_args(argv)
    if not any([args.trade_id, args.signal_id, args.order_id]):
        p.error("Provide --trade-id, --signal-id, or --order-id")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
