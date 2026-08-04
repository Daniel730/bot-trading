"""Reconstruct a trade end-to-end from durable stores (Phase-5 observability).

Joins TradeLedger + AgentReasoning + TradeJournal + execution_intents +
on-disk decision packs / WAL references. Broker is consulted when available
but reconstruction must work offline from local truth + provenance.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, text

from src.services.persistence_service import (
    AgentReasoning,
    TradeJournal,
    TradeLedger,
    persistence_service,
)
from src.services.trade_provenance import build_provenance

logger = logging.getLogger(__name__)


def _enum_val(v: Any) -> Any:
    return getattr(v, "value", v)


def _row_to_dict(row: TradeLedger) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "order_id": row.order_id,
        "signal_id": str(row.signal_id) if row.signal_id else None,
        "ticker": row.ticker,
        "side": _enum_val(row.side),
        "quantity": float(row.quantity or 0),
        "price": float(row.price or 0),
        "fee": float(row.fee or 0),
        "status": _enum_val(row.status),
        "venue": row.venue,
        "execution_lane": row.execution_lane,
        "is_shadow": row.is_shadow,
        "execution_timestamp": row.execution_timestamp.isoformat()
        if row.execution_timestamp
        else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "metadata": row.metadata_json if isinstance(row.metadata_json, dict) else {},
    }


async def reconstruct_trade(
    *,
    trade_id: Optional[str] = None,
    signal_id: Optional[str] = None,
    order_id: Optional[str] = None,
    incident_pack_dir: str | Path = "data/incident_packs",
) -> dict[str, Any]:
    """Build a forensic pack for one trade/signal.

    Provide any of trade_id (ledger UUID), signal_id, or order_id / client_order_id.
    """
    if not any([trade_id, signal_id, order_id]):
        raise ValueError("Provide trade_id, signal_id, or order_id")

    await persistence_service.init_db()
    legs: list[TradeLedger] = []
    async with persistence_service.AsyncSessionLocal() as session:
        if trade_id:
            row = await session.get(TradeLedger, uuid.UUID(str(trade_id)))
            if row is None:
                raise LookupError(f"trade_id not found: {trade_id}")
            signal_id = str(row.signal_id) if row.signal_id else signal_id
            if row.signal_id:
                legs = (
                    await session.execute(
                        select(TradeLedger).where(TradeLedger.signal_id == row.signal_id)
                    )
                ).scalars().all()
            else:
                legs = [row]
        elif signal_id:
            sid = uuid.UUID(str(signal_id))
            legs = (
                await session.execute(select(TradeLedger).where(TradeLedger.signal_id == sid))
            ).scalars().all()
        else:
            oid = str(order_id)
            by_order = (
                await session.execute(select(TradeLedger).where(TradeLedger.order_id == oid))
            ).scalars().all()
            if by_order:
                legs = list(by_order)
            else:
                # client_order_id often lives only in metadata until attach.
                recent = (
                    await session.execute(
                        select(TradeLedger).order_by(TradeLedger.execution_timestamp.desc()).limit(2000)
                    )
                ).scalars().all()
                legs = [
                    r
                    for r in recent
                    if isinstance(r.metadata_json, dict)
                    and str(r.metadata_json.get("client_order_id")) == oid
                ]

        if not legs:
            raise LookupError("No ledger rows matched the query")

        sid = legs[0].signal_id
        reasoning = []
        journal = None
        if sid is not None:
            reasoning = (
                await session.execute(
                    select(AgentReasoning).where(AgentReasoning.trace_id == sid)
                )
            ).scalars().all()
            journal = (
                await session.execute(
                    select(TradeJournal).where(TradeJournal.signal_id == sid)
                )
            ).scalars().first()

    intents: list[dict[str, Any]] = []
    try:
        from src.services.distributed_reservation import distributed_reservation_store

        await distributed_reservation_store.ensure_schema()
        async with persistence_service.AsyncSessionLocal() as session:
            if sid is not None:
                rows = (
                    await session.execute(
                        text(
                            """
                            SELECT client_order_id, signal_id, leg, status,
                                   broker_order_id, created_at, updated_at, metadata
                            FROM execution_intents
                            WHERE signal_id = :sid
                            ORDER BY leg
                            """
                        ),
                        {"sid": sid},
                    )
                ).mappings().all()
                intents = [dict(r) for r in rows]
                for item in intents:
                    for k, v in list(item.items()):
                        if hasattr(v, "isoformat"):
                            item[k] = v.isoformat()
                        elif isinstance(v, uuid.UUID):
                            item[k] = str(v)
    except Exception as exc:  # noqa: BLE001
        logger.debug("execution_intents unavailable: %s", exc)

    pack_hits: list[str] = []
    pack_root = Path(incident_pack_dir)
    if sid is not None and pack_root.exists():
        needle = str(sid)
        for path in pack_root.rglob("*.json"):
            try:
                if needle in path.read_text(encoding="utf-8", errors="ignore"):
                    pack_hits.append(str(path))
            except Exception:  # noqa: BLE001
                continue

    provenance = {}
    for leg in legs:
        meta = leg.metadata_json if isinstance(leg.metadata_json, dict) else {}
        if isinstance(meta.get("provenance"), dict):
            provenance = meta["provenance"]
            break

    result = {
        "reconstructed_at": datetime.now(timezone.utc).isoformat(),
        "query": {
            "trade_id": trade_id,
            "signal_id": str(sid) if sid else signal_id,
            "order_id": order_id,
        },
        "provenance": provenance or build_provenance(),
        "runtime_provenance_now": build_provenance(),
        "legs": [_row_to_dict(r) for r in legs],
        "agent_reasoning": [
            {
                "id": str(r.id),
                "agent_name": r.agent_name,
                "ticker_pair": r.ticker_pair,
                "decision": _enum_val(r.decision),
                "thought_journal": r.thought_journal,
                "risk_metrics": r.risk_metrics,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reasoning
        ],
        "trade_journal": (
            {
                "id": str(journal.id),
                "entry_regime": _enum_val(journal.entry_regime),
                "exit_reason": _enum_val(journal.exit_reason),
                "efficiency_score": float(journal.efficiency_score)
                if journal.efficiency_score is not None
                else None,
                "reflection_text": journal.reflection_text,
                "metrics_at_entry": journal.metrics_at_entry,
            }
            if journal
            else None
        ),
        "execution_intents": intents,
        "incident_packs": pack_hits[:20],
        "reconstruction_notes": [
            "Broker fills: re-query Alpaca by client_order_id in legs[].metadata when online.",
            "Decision ring buffer is process-local; prefer exported incident packs for historical AI trail.",
            "Compare provenance.git_commit / config_hash against runtime_provenance_now for drift.",
        ],
    }
    try:
        from src.services.decision_package import decision_package_from_reconstruction

        result["decision_package"] = decision_package_from_reconstruction(result)
    except Exception as exc:  # noqa: BLE001
        logger.debug("decision_package build skipped: %s", exc)
    return result
