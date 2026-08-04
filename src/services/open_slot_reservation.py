"""Durable open-slot reservations (audit F-015) + append-only intent WAL (F-020).

Claim a pair/leg slot *before* ``request_approval`` and hold it through
``execute_trade`` so concurrent approvals cannot double-open the same legs
or exceed ``MAX_OPEN_PAIRS``.

The WAL is an append-only JSONL file with per-record checksums. Recovery
replays CLAIM/RELEASE ops idempotently after crash.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from src.config import settings
from src.services.portfolio_book_guards import (
    canonical_book_symbol,
    check_max_open_pairs,
    find_shared_leg_conflict,
)

logger = logging.getLogger(__name__)

DEFAULT_WAL_PATH = Path("data/audit/open_slot_reservations.wal")
# Approvals can wait up to 300s; keep a buffer for execute_trade.
DEFAULT_TTL_SECONDS = 600.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_pair_key(ticker_a: str, ticker_b: str) -> str:
    a = canonical_book_symbol(ticker_a)
    b = canonical_book_symbol(ticker_b)
    left, right = sorted((a, b))
    return f"{left}|{right}"


def _checksum(payload: Mapping[str, Any]) -> str:
    """Stable checksum over the record excluding the checksum field itself."""
    body = {k: v for k, v in payload.items() if k != "checksum"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass
class Reservation:
    signal_id: str
    ticker_a: str
    ticker_b: str
    legs: tuple[str, ...]
    claimed_at: float
    expires_at: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def pair_key(self) -> str:
        return _canonical_pair_key(self.ticker_a, self.ticker_b)

    def to_open_signal_shape(self) -> dict[str, Any]:
        """Shape compatible with ``find_shared_leg_conflict`` / open-signal scans."""
        return {
            "signal_id": self.signal_id,
            "legs": [{"ticker": leg} for leg in self.legs],
            "reservation": True,
        }


class TradeIntentWAL:
    """Append-only, checksummed, replayable intent log (F-020)."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or getattr(settings, "OPEN_SLOT_WAL_PATH", None) or DEFAULT_WAL_PATH)
        self._lock = threading.Lock()
        self._seq = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self._seq = self._recover_seq()

    def _recover_seq(self) -> int:
        last = 0
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    try:
                        last = max(last, int(rec.get("seq") or 0))
                    except (TypeError, ValueError):
                        continue
        except FileNotFoundError:
            return 0
        return last

    def append(self, op: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            record = {
                "seq": self._seq,
                "op": op,
                "ts": _utcnow().isoformat(),
                **dict(payload),
            }
            record["checksum"] = _checksum(record)
            line = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            return record

    def iter_records(self) -> Iterable[dict[str, Any]]:
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("TradeIntentWAL: skipping corrupt line")
                        continue
                    expected = _checksum(rec)
                    if rec.get("checksum") != expected:
                        logger.warning(
                            "TradeIntentWAL: checksum mismatch seq=%s — skipping",
                            rec.get("seq"),
                        )
                        continue
                    yield rec
        except FileNotFoundError:
            return


class OpenSlotReservationService:
    """Reservation facade: PostgreSQL distributed store is authority (Phase-4).

    In-process state is a non-authoritative cache for fast local reads only.
    ``claim`` / ``release`` always go through ``DistributedReservationStore``
    when available — never a Python mutex as the safety boundary.
    """

    def __init__(
        self,
        *,
        wal: TradeIntentWAL | None = None,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        distributed=None,
        prefer_distributed: bool = True,
    ):
        self.wal = wal or TradeIntentWAL()
        self.ttl_seconds = float(ttl_seconds)
        self._lock = asyncio.Lock()  # local cache only — NOT the safety lock
        self._by_signal: dict[str, Reservation] = {}
        self.prefer_distributed = prefer_distributed
        self._distributed = distributed
        self._replay_from_wal()

    @property
    def distributed(self):
        if self._distributed is not None:
            return self._distributed
        if not self.prefer_distributed:
            return None
        try:
            from src.services.distributed_reservation import distributed_reservation_store

            return distributed_reservation_store
        except Exception:  # noqa: BLE001
            return None

    def _replay_from_wal(self) -> None:
        active: dict[str, Reservation] = {}
        now = time.time()
        for rec in self.wal.iter_records():
            op = str(rec.get("op") or "").upper()
            signal_id = str(rec.get("signal_id") or "").strip()
            if not signal_id:
                continue
            if op == "CLAIM":
                expires = float(rec.get("expires_at") or (now + self.ttl_seconds))
                if expires < now:
                    continue
                legs = tuple(str(x) for x in (rec.get("legs") or []))
                active[signal_id] = Reservation(
                    signal_id=signal_id,
                    ticker_a=str(rec.get("ticker_a") or ""),
                    ticker_b=str(rec.get("ticker_b") or ""),
                    legs=legs,
                    claimed_at=float(rec.get("claimed_at") or now),
                    expires_at=expires,
                    metadata=dict(rec.get("metadata") or {}),
                )
            elif op == "RELEASE":
                active.pop(signal_id, None)
        self._by_signal = active
        logger.info(
            "OpenSlotReservationService: replayed WAL — %s active reservation(s)",
            len(self._by_signal),
        )

    def _purge_expired_unlocked(self) -> None:
        now = time.time()
        expired = [sid for sid, res in self._by_signal.items() if res.expires_at <= now]
        for sid in expired:
            self._by_signal.pop(sid, None)
            try:
                self.wal.append("RELEASE", {"signal_id": sid, "reason": "ttl_expired"})
            except Exception as exc:  # noqa: BLE001
                logger.warning("OpenSlotReservationService: WAL release failed: %s", exc)

    def active_as_open_signals(self) -> list[dict[str, Any]]:
        """Sync cache view — prefer ``active_as_open_signals_async`` for authority."""
        self._purge_expired_unlocked()
        return [res.to_open_signal_shape() for res in self._by_signal.values()]

    async def active_as_open_signals_async(self) -> list[dict[str, Any]]:
        dist = self.distributed
        if dist is not None:
            try:
                return await dist.active_as_open_signals()
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Distributed reservation read failed — fail-closed empty merge: %s",
                    exc,
                )
                # Fail closed: treat as max contention rather than empty book.
                raise
        return self.active_as_open_signals()

    def reservation_count(self) -> int:
        self._purge_expired_unlocked()
        return len(self._by_signal)

    async def reservation_count_async(self) -> int:
        dist = self.distributed
        if dist is not None:
            return await dist.reservation_count()
        return self.reservation_count()

    async def claim(
        self,
        *,
        signal_id: str,
        ticker_a: str,
        ticker_b: str,
        open_signals: Sequence[Mapping[str, Any]] | None,
        canonicalize=canonical_book_symbol,
        max_open_pairs: Optional[int] = None,
        block_shared_legs: Optional[bool] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Claim via Postgres when available; else local+WAL fallback (tests/dev)."""
        sid = str(signal_id or "").strip()
        if not sid:
            return {"ok": False, "reason": "missing_signal_id"}

        dist = self.distributed
        if dist is not None:
            try:
                result = await dist.claim(
                    signal_id=sid,
                    ticker_a=ticker_a,
                    ticker_b=ticker_b,
                    open_signal_count=len(open_signals or []),
                    open_signal_legs=open_signals,
                    canonicalize=canonicalize,
                    max_open_pairs=max_open_pairs,
                    block_shared_legs=block_shared_legs,
                    metadata=metadata,
                )
                if result.get("ok"):
                    now = time.time()
                    legs = (canonicalize(ticker_a), canonicalize(ticker_b))
                    self._by_signal[sid] = Reservation(
                        signal_id=sid,
                        ticker_a=str(ticker_a),
                        ticker_b=str(ticker_b),
                        legs=legs,
                        claimed_at=now,
                        expires_at=now + self.ttl_seconds,
                        metadata=dict(metadata or {}),
                    )
                    try:
                        self.wal.append(
                            "CLAIM",
                            {
                                "signal_id": sid,
                                "ticker_a": ticker_a,
                                "ticker_b": ticker_b,
                                "legs": list(legs),
                                "claimed_at": now,
                                "expires_at": now + self.ttl_seconds,
                                "metadata": dict(metadata or {}),
                                "backend": "postgres",
                            },
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("WAL mirror CLAIM failed: %s", exc)
                return result
            except Exception as exc:  # noqa: BLE001
                logger.critical(
                    "Distributed reservation unavailable — refusing claim (fail-closed): %s",
                    exc,
                )
                return {"ok": False, "reason": "distributed_reservation_unavailable", "detail": str(exc)}

        # Local fallback for unit tests without Postgres.
        return await self._claim_local(
            signal_id=sid,
            ticker_a=ticker_a,
            ticker_b=ticker_b,
            open_signals=open_signals,
            canonicalize=canonicalize,
            max_open_pairs=max_open_pairs,
            block_shared_legs=block_shared_legs,
            metadata=metadata,
        )

    async def _claim_local(
        self,
        *,
        signal_id: str,
        ticker_a: str,
        ticker_b: str,
        open_signals: Sequence[Mapping[str, Any]] | None,
        canonicalize=canonical_book_symbol,
        max_open_pairs: Optional[int] = None,
        block_shared_legs: Optional[bool] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        async with self._lock:
            self._purge_expired_unlocked()
            if signal_id in self._by_signal:
                return {"ok": True, "reason": "already_held", "reservation": self._by_signal[signal_id]}

            legs = (canonicalize(ticker_a), canonicalize(ticker_b))
            if not legs[0] or not legs[1] or legs[0] == legs[1]:
                return {"ok": False, "reason": "invalid_legs"}

            combined = list(open_signals or []) + self.active_as_open_signals()
            max_pairs = int(
                max_open_pairs
                if max_open_pairs is not None
                else getattr(settings, "MAX_OPEN_PAIRS", 8)
            )
            slot = check_max_open_pairs(len(combined), max_pairs)
            if not slot["allowed"]:
                return {"ok": False, "reason": "max_open_pairs_guard", "detail": slot["reason"]}

            pair_symbols = {legs[0], legs[1]}
            for signal in combined:
                existing_legs = {
                    canonicalize(leg.get("ticker"))
                    for leg in (signal.get("legs") or [])
                    if isinstance(leg, Mapping) and leg.get("ticker")
                }
                if pair_symbols.issubset(existing_legs):
                    return {
                        "ok": False,
                        "reason": "pair_already_open_or_reserved",
                        "conflict_signal_id": signal.get("signal_id"),
                    }

            use_shared = (
                block_shared_legs
                if block_shared_legs is not None
                else bool(getattr(settings, "BLOCK_SHARED_LEG_OPENS", True))
            )
            if use_shared:
                conflict = find_shared_leg_conflict(
                    ticker_a,
                    ticker_b,
                    combined,
                    canonicalize=canonicalize,
                )
                if conflict:
                    return {
                        "ok": False,
                        "reason": "shared_leg_guard",
                        "detail": conflict,
                    }

            now = time.time()
            res = Reservation(
                signal_id=signal_id,
                ticker_a=str(ticker_a),
                ticker_b=str(ticker_b),
                legs=legs,
                claimed_at=now,
                expires_at=now + self.ttl_seconds,
                metadata=dict(metadata or {}),
            )
            self.wal.append(
                "CLAIM",
                {
                    "signal_id": signal_id,
                    "ticker_a": res.ticker_a,
                    "ticker_b": res.ticker_b,
                    "legs": list(res.legs),
                    "claimed_at": res.claimed_at,
                    "expires_at": res.expires_at,
                    "metadata": res.metadata,
                    "backend": "local",
                },
            )
            self._by_signal[signal_id] = res
            return {"ok": True, "reason": "claimed", "reservation": res}

    async def release(self, signal_id: str, *, reason: str = "released") -> bool:
        sid = str(signal_id or "").strip()
        dist = self.distributed
        existed = False
        if dist is not None:
            try:
                existed = await dist.release(sid, reason=reason)
            except Exception as exc:  # noqa: BLE001
                logger.error("Distributed release failed: %s", exc)
        async with self._lock:
            local_existed = sid in self._by_signal
            self._by_signal.pop(sid, None)
            if existed or local_existed:
                try:
                    self.wal.append("RELEASE", {"signal_id": sid, "reason": reason})
                except Exception as exc:  # noqa: BLE001
                    logger.warning("WAL RELEASE failed: %s", exc)
            return existed or local_existed

    def has(self, signal_id: str) -> bool:
        self._purge_expired_unlocked()
        return str(signal_id) in self._by_signal

    async def has_async(self, signal_id: str) -> bool:
        dist = self.distributed
        if dist is not None:
            return await dist.has(signal_id)
        return self.has(signal_id)


open_slot_reservation_service = OpenSlotReservationService()
