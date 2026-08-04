"""Phase-4 distributed open-slot reservation (R-301).

Authority is PostgreSQL — not process memory, globals, or Python locks.

Claim algorithm (single transaction):
1. ``pg_advisory_xact_lock`` serializes claimers across processes
2. Expire stale ACTIVE rows
3. Count ACTIVE reservations (+ optional ledger open count)
4. Reject shared-leg / max-pairs / duplicate pair via unique indexes + checks
5. INSERT ACTIVE row (unique on signal_id; partial unique on each active leg)
6. COMMIT — survives restart / SIGKILL / reboot

File WAL remains an append-only audit mirror (not the lock authority).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import text

from src.config import settings
from src.services.portfolio_book_guards import (
    canonical_book_symbol,
    check_max_open_pairs,
)

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 600.0
ADVISORY_LOCK_KEY = 0x4F50454E_534C4F54  # "OPEN SLOT" packed


def _instance_id() -> str:
    return (
        os.getenv("BOT_INSTANCE_ID")
        or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _pair_key(leg_a: str, leg_b: str) -> str:
    left, right = sorted((leg_a, leg_b))
    return f"{left}|{right}"


RESERVATION_DDL = """
CREATE TABLE IF NOT EXISTS open_slot_reservations (
    signal_id TEXT PRIMARY KEY,
    ticker_a TEXT NOT NULL,
    ticker_b TEXT NOT NULL,
    leg_a TEXT NOT NULL,
    leg_b TEXT NOT NULL,
    pair_key TEXT NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    holder_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_open_slot_status_expires
    ON open_slot_reservations (status, expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_open_slot_leg_a_active
    ON open_slot_reservations (leg_a) WHERE status = 'ACTIVE';
CREATE UNIQUE INDEX IF NOT EXISTS uq_open_slot_leg_b_active
    ON open_slot_reservations (leg_b) WHERE status = 'ACTIVE';
CREATE UNIQUE INDEX IF NOT EXISTS uq_open_slot_pair_active
    ON open_slot_reservations (pair_key) WHERE status = 'ACTIVE';
"""

EXECUTION_INTENT_DDL = """
CREATE TABLE IF NOT EXISTS execution_intents (
    client_order_id TEXT PRIMARY KEY,
    signal_id UUID NOT NULL,
    leg CHAR(1) NOT NULL,
    status TEXT NOT NULL DEFAULT 'INTENT',
    broker_order_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_execution_intent_signal_leg UNIQUE (signal_id, leg)
);
CREATE INDEX IF NOT EXISTS ix_execution_intents_signal
    ON execution_intents (signal_id);
CREATE INDEX IF NOT EXISTS ix_execution_intents_status
    ON execution_intents (status);
"""


class DistributedReservationStore:
    """PostgreSQL-backed reservation store shared by all bot instances."""

    def __init__(self, session_factory=None, *, ttl_seconds: float = DEFAULT_TTL_SECONDS):
        self._session_factory = session_factory
        self.ttl_seconds = float(ttl_seconds)
        self.holder_id = _instance_id()
        self._schema_ready = False

    def _sessions(self):
        if self._session_factory is not None:
            return self._session_factory
        from src.services.persistence_service import persistence_service

        return persistence_service.AsyncSessionLocal

    async def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        from src.services.persistence_service import persistence_service

        async with persistence_service.engine.begin() as conn:
            for stmt in RESERVATION_DDL.strip().split(";"):
                sql = stmt.strip()
                if sql:
                    await conn.execute(text(sql))
            for stmt in EXECUTION_INTENT_DDL.strip().split(";"):
                sql = stmt.strip()
                if sql:
                    await conn.execute(text(sql))
        self._schema_ready = True

    async def active_as_open_signals(self) -> list[dict[str, Any]]:
        await self.ensure_schema()
        async with self._sessions()() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE open_slot_reservations
                        SET status = 'RELEASED'
                        WHERE status = 'ACTIVE' AND expires_at <= NOW()
                        """
                    )
                )
                rows = (
                    await session.execute(
                        text(
                            """
                            SELECT signal_id, leg_a, leg_b
                            FROM open_slot_reservations
                            WHERE status = 'ACTIVE'
                            """
                        )
                    )
                ).mappings().all()
        return [
            {
                "signal_id": r["signal_id"],
                "legs": [{"ticker": r["leg_a"]}, {"ticker": r["leg_b"]}],
                "reservation": True,
            }
            for r in rows
        ]

    async def reservation_count(self) -> int:
        await self.ensure_schema()
        async with self._sessions()() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) AS c FROM open_slot_reservations WHERE status = 'ACTIVE'"
                    )
                )
            ).mappings().one()
            return int(row["c"])

    async def has(self, signal_id: str) -> bool:
        await self.ensure_schema()
        async with self._sessions()() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT 1 FROM open_slot_reservations
                        WHERE signal_id = :sid AND status = 'ACTIVE' AND expires_at > NOW()
                        LIMIT 1
                        """
                    ),
                    {"sid": str(signal_id)},
                )
            ).first()
            return row is not None

    async def claim(
        self,
        *,
        signal_id: str,
        ticker_a: str,
        ticker_b: str,
        open_signal_count: int = 0,
        open_signal_legs: Sequence[Mapping[str, Any]] | None = None,
        canonicalize=canonical_book_symbol,
        max_open_pairs: Optional[int] = None,
        block_shared_legs: Optional[bool] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        sid = str(signal_id or "").strip()
        if not sid:
            return {"ok": False, "reason": "missing_signal_id"}

        leg_a = canonicalize(ticker_a)
        leg_b = canonicalize(ticker_b)
        if not leg_a or not leg_b or leg_a == leg_b:
            return {"ok": False, "reason": "invalid_legs"}

        max_pairs = int(
            max_open_pairs
            if max_open_pairs is not None
            else getattr(settings, "MAX_OPEN_PAIRS", 8)
        )
        use_shared = (
            block_shared_legs
            if block_shared_legs is not None
            else bool(getattr(settings, "BLOCK_SHARED_LEG_OPENS", True))
        )
        pair_key = _pair_key(leg_a, leg_b)
        now = _utcnow()
        expires = now + timedelta(seconds=self.ttl_seconds)
        meta_json = json.dumps(dict(metadata or {}), default=str)

        await self.ensure_schema()
        async with self._sessions()() as session:
            async with session.begin():
                # Cross-process serialization — not a Python mutex.
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(:k)"),
                    {"k": ADVISORY_LOCK_KEY},
                )
                await session.execute(
                    text(
                        """
                        UPDATE open_slot_reservations
                        SET status = 'RELEASED'
                        WHERE status = 'ACTIVE' AND expires_at <= NOW()
                        """
                    )
                )

                existing = (
                    await session.execute(
                        text(
                            """
                            SELECT signal_id, status FROM open_slot_reservations
                            WHERE signal_id = :sid
                            """
                        ),
                        {"sid": sid},
                    )
                ).mappings().first()
                if existing and existing["status"] == "ACTIVE":
                    return {"ok": True, "reason": "already_held", "signal_id": sid}

                active_count = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) AS c FROM open_slot_reservations WHERE status = 'ACTIVE'"
                        )
                    )
                ).mappings().one()["c"]
                slot = check_max_open_pairs(int(open_signal_count) + int(active_count), max_pairs)
                if not slot["allowed"]:
                    return {
                        "ok": False,
                        "reason": "max_open_pairs_guard",
                        "detail": slot["reason"],
                    }

                pair_hit = (
                    await session.execute(
                        text(
                            """
                            SELECT signal_id FROM open_slot_reservations
                            WHERE status = 'ACTIVE' AND pair_key = :pk
                            LIMIT 1
                            """
                        ),
                        {"pk": pair_key},
                    )
                ).first()
                if pair_hit:
                    return {
                        "ok": False,
                        "reason": "pair_already_open_or_reserved",
                        "conflict_signal_id": pair_hit[0],
                    }

                if use_shared:
                    conflict = (
                        await session.execute(
                            text(
                                """
                                SELECT signal_id, leg_a, leg_b
                                FROM open_slot_reservations
                                WHERE status = 'ACTIVE'
                                  AND (leg_a IN (:la, :lb) OR leg_b IN (:la, :lb))
                                LIMIT 1
                                FOR UPDATE
                                """
                            ),
                            {"la": leg_a, "lb": leg_b},
                        )
                    ).mappings().first()
                    if conflict:
                        return {
                            "ok": False,
                            "reason": "shared_leg_guard",
                            "detail": {
                                "conflict_signal_id": conflict["signal_id"],
                                "legs": [conflict["leg_a"], conflict["leg_b"]],
                            },
                        }
                    # Also check ledger-shaped open signals passed by caller.
                    for signal in open_signal_legs or []:
                        existing_legs = {
                            canonicalize(leg.get("ticker"))
                            for leg in (signal.get("legs") or [])
                            if isinstance(leg, Mapping) and leg.get("ticker")
                        }
                        if {leg_a, leg_b} & existing_legs:
                            return {
                                "ok": False,
                                "reason": "shared_leg_guard",
                                "detail": {
                                    "conflict_signal_id": signal.get("signal_id"),
                                    "legs": sorted(existing_legs),
                                },
                            }

                if existing and existing["status"] == "RELEASED":
                    await session.execute(
                        text(
                            """
                            UPDATE open_slot_reservations SET
                                ticker_a = :ta, ticker_b = :tb,
                                leg_a = :la, leg_b = :lb, pair_key = :pk,
                                claimed_at = :ca, expires_at = :ea,
                                holder_id = :hid, status = 'ACTIVE',
                                metadata = CAST(:meta AS jsonb)
                            WHERE signal_id = :sid
                            """
                        ),
                        {
                            "sid": sid,
                            "ta": str(ticker_a),
                            "tb": str(ticker_b),
                            "la": leg_a,
                            "lb": leg_b,
                            "pk": pair_key,
                            "ca": now,
                            "ea": expires,
                            "hid": self.holder_id,
                            "meta": meta_json,
                        },
                    )
                else:
                    try:
                        await session.execute(
                            text(
                                """
                                INSERT INTO open_slot_reservations (
                                    signal_id, ticker_a, ticker_b, leg_a, leg_b, pair_key,
                                    claimed_at, expires_at, holder_id, status, metadata
                                ) VALUES (
                                    :sid, :ta, :tb, :la, :lb, :pk,
                                    :ca, :ea, :hid, 'ACTIVE', CAST(:meta AS jsonb)
                                )
                                """
                            ),
                            {
                                "sid": sid,
                                "ta": str(ticker_a),
                                "tb": str(ticker_b),
                                "la": leg_a,
                                "lb": leg_b,
                                "pk": pair_key,
                                "ca": now,
                                "ea": expires,
                                "hid": self.holder_id,
                                "meta": meta_json,
                            },
                        )
                    except Exception as exc:  # noqa: BLE001 — unique violation = race lost
                        logger.info("Distributed claim lost race: %s", exc)
                        return {"ok": False, "reason": "unique_constraint_race", "detail": str(exc)}

        return {"ok": True, "reason": "claimed", "signal_id": sid, "holder_id": self.holder_id}

    async def release(self, signal_id: str, *, reason: str = "released") -> bool:
        await self.ensure_schema()
        async with self._sessions()() as session:
            async with session.begin():
                result = await session.execute(
                    text(
                        """
                        UPDATE open_slot_reservations
                        SET status = 'RELEASED',
                            metadata = metadata || jsonb_build_object(
                                'release_reason', CAST(:reason AS text)
                            )
                        WHERE signal_id = :sid AND status = 'ACTIVE'
                        """
                    ),
                    {"sid": str(signal_id), "reason": reason},
                )
                return bool(result.rowcount)


distributed_reservation_store = DistributedReservationStore()
