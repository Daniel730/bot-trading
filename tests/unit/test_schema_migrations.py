"""Schema drift / additive migration safety tests (no live Postgres required)."""

from __future__ import annotations

import sqlite3
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.persistence import PersistenceManager
from src.services.persistence_service import (
    OrderSide,
    OrderStatus,
    TradeLedger,
    UniverseCandidate,
    PersistenceService,
)
from src.services.schema_migrations import (
    POSTGRES_ADDITIVE_COLUMNS,
    POSTGRES_BACKFILLS,
    POSTGRES_INDEXES,
    SQLITE_ADDITIVE_COLUMNS,
    apply_postgres_migrations,
    ensure_sqlite_columns,
    sqlite_existing_columns,
)


def test_postgres_migrations_cover_lane_and_signal_columns():
    cols = {(table, column) for table, column, _ in POSTGRES_ADDITIVE_COLUMNS}
    assert ("trade_ledger", "signal_id") in cols
    assert ("trade_ledger", "execution_lane") in cols
    assert ("trade_ledger", "is_shadow") in cols
    assert ("trade_ledger", "venue") in cols
    assert ("trade_ledger", "closed_at") in cols
    assert ("universe_candidates", "hedge_ratio") in cols
    assert ("trade_journal", "signal_id") in cols
    assert any("ix_trade_ledger_signal_id" in sql for sql in POSTGRES_INDEXES)
    assert any("ix_trade_ledger_execution_lane" in sql for sql in POSTGRES_INDEXES)
    assert POSTGRES_BACKFILLS  # legacy metadata → columns


def test_postgres_lane_backfills_cast_metadata_to_jsonb():
    """metadata may be JSON (not JSONB); ? / ->> must go through ::jsonb."""
    joined = "\n".join(POSTGRES_BACKFILLS)
    assert "metadata::jsonb ? 'is_shadow'" in joined
    assert "metadata::jsonb ? 'execution_lane'" in joined
    assert "metadata::jsonb->>'is_shadow'" in joined
    assert "metadata::jsonb->>'execution_lane'" in joined
    # Bare json ? would fail on older bot-server volumes.
    assert "AND metadata ? " not in joined
    assert "WHEN metadata->>" not in joined


def test_trade_ledger_orm_exposes_lane_and_signal_columns():
    assert hasattr(TradeLedger, "signal_id")
    assert hasattr(TradeLedger, "execution_lane")
    assert hasattr(TradeLedger, "is_shadow")


def test_universe_candidate_accepts_hedge_ratio():
    candidate = UniverseCandidate(
        pair_id="BTC-USD_ETH-USD",
        sector="Crypto",
        p_value=0.01,
        correlation=0.9,
        expected_return=0.1,
        volatility=0.2,
        sortino=1.5,
        hedge_ratio=14.5,
    )
    assert float(candidate.hedge_ratio) == 14.5


def test_sqlite_ensure_columns_adds_missing_thought_journal_fields(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    # Simulate an older volume missing newer thought_journal columns.
    conn.execute(
        "CREATE TABLE thought_journal (signal_id TEXT PRIMARY KEY, bull TEXT, bear TEXT)"
    )
    conn.commit()
    before = sqlite_existing_columns(conn, "thought_journal")
    assert "fundamental_impact" not in before
    assert "sec_ref" not in before

    applied = ensure_sqlite_columns(conn)
    conn.commit()
    after = sqlite_existing_columns(conn, "thought_journal")
    conn.close()

    assert "thought_journal.fundamental_impact" in applied
    assert "thought_journal.sec_ref" in applied
    assert "fundamental_impact" in after
    assert "sec_ref" in after


def test_sqlite_ensure_columns_is_idempotent(tmp_path):
    db_path = tmp_path / "fresh.db"
    mgr = PersistenceManager(str(db_path))
    conn = mgr._connect()
    assert ensure_sqlite_columns(conn) == []
    conn.close()


def test_sqlite_additive_catalog_covers_logs_signal_id_and_thought_fields():
    assert "signal_id" in SQLITE_ADDITIVE_COLUMNS["logs"]
    assert "fundamental_impact" in SQLITE_ADDITIVE_COLUMNS["thought_journal"]
    assert "sec_ref" in SQLITE_ADDITIVE_COLUMNS["thought_journal"]


@pytest.mark.asyncio
async def test_apply_postgres_migrations_emits_alter_for_lane_columns():
    executed: list[str] = []

    class _Conn:
        async def execute(self, statement):
            executed.append(str(statement))

    await apply_postgres_migrations(
        _Conn(),  # type: ignore[arg-type]
        order_status_values=["OPEN_PAIR", "CLOSING"],
    )
    joined = "\n".join(executed)
    assert "ADD COLUMN IF NOT EXISTS signal_id" in joined
    assert "ADD COLUMN IF NOT EXISTS execution_lane" in joined
    assert "ADD COLUMN IF NOT EXISTS is_shadow" in joined
    assert "ADD COLUMN IF NOT EXISTS hedge_ratio" in joined
    assert "ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'OPEN_PAIR'" in joined
    assert "metadata::jsonb ?" in joined
    assert "metadata::jsonb->>" in joined


@pytest.mark.asyncio
async def test_log_trade_dual_writes_lane_columns(monkeypatch):
    captured: dict = {}

    session = MagicMock()
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=session)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = begin_cm
    session.add.side_effect = lambda trade: captured.__setitem__("trade", trade)

    service = PersistenceService()
    monkeypatch.setattr(service, "AsyncSessionLocal", lambda: session_cm)
    monkeypatch.setattr(
        "src.services.persistence_service.settings",
        SimpleNamespace(
            execution_lane="SHADOW",
            is_broker_paper_trading=False,
        ),
    )

    signal_id = str(uuid.uuid4())
    await service.log_trade(
        {
            "order_id": "shadow-1",
            "signal_id": signal_id,
            "ticker": "BTC-USD",
            "side": OrderSide.BUY,
            "quantity": 0.01,
            "price": 50000.0,
            "status": OrderStatus.OPEN_PAIR,
            "metadata_json": {"is_shadow": True, "execution_lane": "SHADOW"},
        }
    )

    trade = captured["trade"]
    assert trade.execution_lane == "SHADOW"
    assert trade.is_shadow is True
    assert trade.metadata_json["execution_lane"] == "SHADOW"
    assert trade.metadata_json["is_shadow"] is True
    assert str(trade.signal_id) == signal_id


@pytest.mark.asyncio
async def test_get_open_signals_prefers_first_class_lane_columns(monkeypatch):
    signal_id = uuid.uuid4()
    row = SimpleNamespace(
        signal_id=signal_id,
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=1.0,
        price=100.0,
        fee=0.0,
        venue="ALPACA",
        execution_timestamp=None,
        metadata_json={"is_shadow": False, "execution_lane": "LIVE"},  # stale meta
        is_shadow=True,
        execution_lane="SHADOW",
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [row]

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, _stmt):
            return _Result()

    service = PersistenceService()
    monkeypatch.setattr(service, "AsyncSessionLocal", lambda: _Session())
    signals = await service.get_open_signals()
    assert len(signals) == 1
    assert signals[0]["is_shadow"] is True
    assert signals[0]["execution_lane"] == "SHADOW"
