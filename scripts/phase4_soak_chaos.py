#!/usr/bin/env python3
"""Phase-4 long soak / chaos harness (operator-run).

Default is a CI-safe lite mode. For the full mandate:

  PYTHONPATH=/workspace .venv/bin/python scripts/phase4_soak_chaos.py \\
      --signals 100000 --hours 48 --chaos 500

Metrics written to data/audit/phase4_soak_metrics.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import resource
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from src.services.distributed_reservation import DistributedReservationStore
from src.services.execution_intent_service import ExecutionIntentService
from src.services.persistence_service import persistence_service


async def run(signals: int, chaos: int, hours: float) -> dict:
    await persistence_service.init_db()
    store = DistributedReservationStore(ttl_seconds=600)
    await store.ensure_schema()
    intents = ExecutionIntentService(store=store)

    async with persistence_service.AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text("DELETE FROM open_slot_reservations"))
            await session.execute(text("DELETE FROM execution_intents"))

    start = time.time()
    deadline = start + hours * 3600
    placed = 0
    dup_rejected = 0
    claim_wins = 0
    claim_losses = 0

    i = 0
    while i < signals and time.time() < deadline:
        sid = uuid.uuid4()
        coid = f"{sid}-A"
        for _ in range(3):
            r = await intents.begin_intent(signal_id=sid, leg="A", client_order_id=coid)
            if r.get("ok"):
                placed += 1
            else:
                dup_rejected += 1
        i += 1
        if i % 500 == 0:
            await asyncio.sleep(0)

    for n in range(chaos):
        a, b = f"C{n}A", f"C{n}B"
        r = await store.claim(
            signal_id=f"chaos-{n}",
            ticker_a=a,
            ticker_b=b,
            open_signal_count=0,
            max_open_pairs=10_000,
            block_shared_legs=False,
        )
        if r.get("ok"):
            claim_wins += 1
            if n % 2 == 0:
                await store.release(f"chaos-{n}", reason="soak")
        else:
            claim_losses += 1

    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    metrics = {
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "signals_attempted": i,
        "intents_placed": placed,
        "duplicate_rejects": dup_rejected,
        "chaos_claim_wins": claim_wins,
        "chaos_claim_losses": claim_losses,
        "open_intents": await intents.count_open_intents(),
        "active_reservations": await store.reservation_count(),
        "elapsed_s": round(time.time() - start, 3),
        "max_rss_kb": rss_kb,
        "invariant_exactly_once": placed == i,
        "invariant_no_dup_intents_per_signal": placed == i,
    }
    out = Path("data/audit/phase4_soak_metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2))
    return metrics


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--signals", type=int, default=2000)
    p.add_argument("--chaos", type=int, default=200)
    p.add_argument("--hours", type=float, default=0.01)
    args = p.parse_args()
    metrics = asyncio.run(run(args.signals, args.chaos, args.hours))
    print(json.dumps(metrics, indent=2))
    if not metrics["invariant_exactly_once"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
