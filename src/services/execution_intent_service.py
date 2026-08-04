"""Exactly-once execution intents (Phase-4).

PostgreSQL unique constraints on ``(signal_id, leg)`` and ``client_order_id``
ensure that even if the same signal is delivered 100× via REST/Telegram/MCP/WS,
only one broker-bound intent row can exist per leg.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Mapping, Optional

from sqlalchemy import text

from src.services.distributed_reservation import distributed_reservation_store

logger = logging.getLogger(__name__)


class ExecutionIntentService:
    def __init__(self, store=None):
        self.store = store or distributed_reservation_store

    async def ensure_schema(self) -> None:
        await self.store.ensure_schema()

    async def begin_intent(
        self,
        *,
        signal_id: str | uuid.UUID,
        leg: str,
        client_order_id: str,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Insert INTENT row. Returns ok=False if already exists (exactly-once)."""
        await self.ensure_schema()
        sid = uuid.UUID(str(signal_id))
        leg_norm = str(leg or "").strip().upper()[:1]
        if leg_norm not in {"A", "B"}:
            return {"ok": False, "reason": "invalid_leg"}
        coid = str(client_order_id or "").strip()
        if not coid:
            return {"ok": False, "reason": "missing_client_order_id"}

        meta = json.dumps(dict(metadata or {}), default=str)
        async with self.store._sessions()() as session:
            async with session.begin():
                inserted = (
                    await session.execute(
                        text(
                            """
                            INSERT INTO execution_intents (
                                client_order_id, signal_id, leg, status, metadata
                            ) VALUES (
                                :c, :sid, :leg, 'INTENT', CAST(:meta AS jsonb)
                            )
                            ON CONFLICT DO NOTHING
                            RETURNING client_order_id
                            """
                        ),
                        {"c": coid, "sid": sid, "leg": leg_norm, "meta": meta},
                    )
                ).first()
                if inserted:
                    return {
                        "ok": True,
                        "reason": "intent_created",
                        "client_order_id": coid,
                    }

                existing = (
                    await session.execute(
                        text(
                            """
                            SELECT client_order_id, status, broker_order_id
                            FROM execution_intents
                            WHERE signal_id = :sid AND leg = :leg
                            """
                        ),
                        {"sid": sid, "leg": leg_norm},
                    )
                ).mappings().first()
                if existing:
                    return {
                        "ok": False,
                        "reason": "duplicate_signal_leg",
                        "existing": dict(existing),
                        "idempotent": True,
                    }
                by_coid = (
                    await session.execute(
                        text(
                            "SELECT signal_id, leg, status FROM execution_intents WHERE client_order_id = :c"
                        ),
                        {"c": coid},
                    )
                ).mappings().first()
                if by_coid:
                    return {
                        "ok": False,
                        "reason": "duplicate_client_order_id",
                        "existing": dict(by_coid),
                        "idempotent": True,
                    }
                # Race: conflict fired but row not visible yet — still idempotent refuse.
                return {
                    "ok": False,
                    "reason": "duplicate_race",
                    "idempotent": True,
                }

    async def mark_submitted(
        self, client_order_id: str, *, broker_order_id: Optional[str] = None
    ) -> None:
        async with self.store._sessions()() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE execution_intents
                        SET status = 'SUBMITTED',
                            broker_order_id = COALESCE(:b, broker_order_id),
                            updated_at = NOW()
                        WHERE client_order_id = :c
                        """
                    ),
                    {"c": client_order_id, "b": broker_order_id},
                )

    async def mark_filled(self, client_order_id: str, *, broker_order_id: Optional[str] = None) -> None:
        async with self.store._sessions()() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE execution_intents
                        SET status = 'FILLED',
                            broker_order_id = COALESCE(:b, broker_order_id),
                            updated_at = NOW()
                        WHERE client_order_id = :c
                        """
                    ),
                    {"c": client_order_id, "b": broker_order_id},
                )

    async def mark_aborted(self, client_order_id: str, *, reason: str = "aborted") -> None:
        async with self.store._sessions()() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE execution_intents
                        SET status = 'ABORTED',
                            metadata = metadata || jsonb_build_object(
                                'abort_reason', CAST(:r AS text)
                            ),
                            updated_at = NOW()
                        WHERE client_order_id = :c AND status IN ('INTENT', 'SUBMITTED')
                        """
                    ),
                    {"c": client_order_id, "r": reason},
                )

    async def count_open_intents(self) -> int:
        await self.ensure_schema()
        async with self.store._sessions()() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*) AS c FROM execution_intents
                        WHERE status IN ('INTENT', 'SUBMITTED')
                        """
                    )
                )
            ).mappings().one()
            return int(row["c"])


execution_intent_service = ExecutionIntentService()
