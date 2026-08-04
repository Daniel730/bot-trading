"""CLI: acknowledge unmanaged Alpaca holdings without creating OPEN ledger signals.

Usage (on bot-server, from repo / container):

  PYTHONPATH=. python scripts/acknowledge_unmanaged_positions.py --list
  PYTHONPATH=. python scripts/acknowledge_unmanaged_positions.py --all
  PYTHONPATH=. python scripts/acknowledge_unmanaged_positions.py --symbols BTC-USD,ETH-USD
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


async def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="Show unmanaged vs acknowledged")
    parser.add_argument("--all", action="store_true", help="Acknowledge every unmanaged symbol")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols to acknowledge")
    parser.add_argument("--note", default="cli_acknowledge", help="Provenance note")
    parser.add_argument("--actor", default="cli", help="Actor label stored with ack")
    args = parser.parse_args(argv)

    from src.services.brokerage_service import brokerage_service
    from src.services.persistence_service import persistence_service
    from src.services.unmanaged_positions_service import (
        acknowledge_symbols,
        classify_broker_positions,
        load_acknowledgements,
    )

    await persistence_service.init_db()
    positions = await brokerage_service.get_positions()
    open_signals = await persistence_service.get_open_signals()
    acks = await load_acknowledgements()
    classified = classify_broker_positions(positions or [], open_signals or [], acks)

    if args.list or (not args.all and not args.symbols):
        print(json.dumps(classified, indent=2, default=str))
        if not args.all and not args.symbols:
            return 0

    targets = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if args.all:
        targets = [row["symbol"] for row in classified["unmanaged"]]
    if not targets:
        print("No unmanaged symbols to acknowledge.", file=sys.stderr)
        return 1

    payload = await acknowledge_symbols(
        symbols=targets,
        positions=positions or [],
        actor=args.actor,
        note=args.note,
    )
    print(json.dumps({"acknowledged": targets, "state": payload}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
