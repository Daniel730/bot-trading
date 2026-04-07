"""
ReconciliationSweeper daemon (feature 033).

Detects Zombie Locks: Redis `execution:inflight:<uuid>` hashes that are
older than ZOMBIE_THRESHOLD_SECONDS and have no committed record in the
PostgreSQL trade_ledger.  A zombie indicates a crashed execution path that
wrote the Redis lock but never completed the DB commit.

On detection the entry is atomically removed from Redis and appended to the
Dead Letter Queue key `dlq:zombie_locks` for manual review or replay.
The sweep runs on a tight SWEEP_INTERVAL_SECONDS loop so the SLA of
"within 10 seconds" is always met.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from src.services.redis_service import redis_service
from src.services.persistence_service import persistence_service, TradeLedger

logger = logging.getLogger(__name__)

ZOMBIE_THRESHOLD_SECONDS = 10
SWEEP_INTERVAL_SECONDS = 5
DLQ_KEY = "dlq:zombie_locks"


class ReconciliationSweeper:

    async def _signal_has_db_record(self, signal_id: uuid.UUID) -> bool:
        """Returns True if the trade_ledger contains at least one row for signal_id."""
        from sqlalchemy import select, exists
        async with persistence_service.AsyncSessionLocal() as session:
            stmt = select(
                exists().where(TradeLedger.signal_id == signal_id)
            )
            result = await session.execute(stmt)
            return result.scalar()

    async def _move_to_dlq(
        self, redis_key: str, signal_id: str, data: dict, age_s: float
    ) -> None:
        entry = json.dumps({
            "signal_id": signal_id,
            "original_data": data,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "age_seconds": round(age_s, 3),
            "reason": "ZOMBIE_LOCK: inflight entry older than "
                      f"{ZOMBIE_THRESHOLD_SECONDS}s with no committed PostgreSQL record",
        })
        # Atomic: push to DLQ and delete the zombie key in one pipeline.
        pipe = redis_service.client.pipeline(transaction=True)
        pipe.lpush(DLQ_KEY, entry)
        pipe.delete(redis_key)
        await pipe.execute()
        logger.warning(
            "ZOMBIE LOCK → DLQ | signal=%s age=%.1fs status=%s",
            signal_id, age_s, data.get("status", "UNKNOWN"),
        )

    async def sweep(self) -> int:
        """
        Scans all inflight keys, promotes zombies to the DLQ.
        Returns the number of zombies evicted in this sweep.
        """
        now_ms = time.time() * 1000
        evicted = 0
        cursor = 0

        while True:
            cursor, keys = await redis_service.client.scan(
                cursor, match="execution:inflight:*", count=200
            )
            for key in keys:
                data = await redis_service.client.hgetall(key)
                if not data:
                    continue

                # Timestamp stored as epoch-milliseconds by RedisOrderSync.java
                try:
                    ts_ms = int(data.get("timestamp", 0))
                except (ValueError, TypeError):
                    continue

                age_s = (now_ms - ts_ms) / 1000.0
                if age_s < ZOMBIE_THRESHOLD_SECONDS:
                    continue

                # Extract UUID from key suffix
                try:
                    signal_id = uuid.UUID(key.split(":")[-1])
                except ValueError:
                    continue

                # Only evict if no matching DB record exists
                if await self._signal_has_db_record(signal_id):
                    continue

                await self._move_to_dlq(key, str(signal_id), data, age_s)
                evicted += 1

            if cursor == 0:
                break

        return evicted

    async def run(self) -> None:
        logger.info(
            "ReconciliationSweeper started — interval=%ds zombie_threshold=%ds dlq=%s",
            SWEEP_INTERVAL_SECONDS, ZOMBIE_THRESHOLD_SECONDS, DLQ_KEY,
        )
        await persistence_service.init_db()
        while True:
            try:
                evicted = await self.sweep()
                if evicted:
                    logger.warning(
                        "ReconciliationSweeper sweep complete — %d zombie(s) moved to DLQ.",
                        evicted,
                    )
            except Exception as exc:
                logger.error("ReconciliationSweeper sweep error: %s", exc)
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    asyncio.run(ReconciliationSweeper().run())
