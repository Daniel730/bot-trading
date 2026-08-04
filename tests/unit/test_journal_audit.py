"""Tests for TradeJournal vs TradeLedger audit continuity."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

import pytest

from src.services.journal_audit_service import (
    audit_journal_vs_ledger,
    classify_journal_ledger_gap,
)
from src.services.persistence_service import (
    ExitReason,
    MarketRegime,
    OrderStatus,
    PersistenceService,
)
from src.services.background_task_watchdog import background_task_watchdog


def test_classify_gap_missing_journal():
    assert (
        classify_journal_ledger_gap(
            signal_id=uuid.uuid4(),
            journal=None,
            ledger_exit_reason=ExitReason.TAKE_PROFIT,
        )
        == "missing_journal"
    )


def test_classify_gap_missing_exit_reason_with_ledger_hint():
    journal = SimpleNamespace(exit_reason=None)
    assert (
        classify_journal_ledger_gap(
            signal_id=uuid.uuid4(),
            journal=journal,
            ledger_exit_reason=ExitReason.STOP_LOSS,
        )
        == "missing_exit_reason"
    )


def test_classify_gap_ok_when_journal_has_exit_reason():
    journal = SimpleNamespace(exit_reason=ExitReason.MANUAL)
    assert (
        classify_journal_ledger_gap(
            signal_id=uuid.uuid4(),
            journal=journal,
            ledger_exit_reason=None,
        )
        is None
    )


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.trade_metadata_updates = []
        self.executed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def begin(self):
        return _FakeTransaction()

    async def execute(self, statement):
        self.executed.append(statement)
        if getattr(statement, "is_select", False):
            return _FakeResult(self.rows)

        if getattr(statement, "is_update", False):
            params = statement.compile().params
            metadata = params.get("metadata") or params.get("metadata_json")
            if metadata is not None:
                self.trade_metadata_updates.append(metadata)

        return SimpleNamespace()


@pytest.mark.asyncio
async def test_close_trade_upserts_journal_exit_reason(monkeypatch):
    signal_id = uuid.uuid4()
    rows = [
        SimpleNamespace(
            id=uuid.uuid4(),
            metadata_json={"broker_order_id": "leg-a-order"},
        ),
    ]
    fake_session = _FakeSession(rows)
    service = PersistenceService()
    monkeypatch.setattr(service, "AsyncSessionLocal", lambda: fake_session)
    ensure = AsyncMock()
    monkeypatch.setattr(service, "ensure_journal_exit_reason", ensure)

    def close_background_coro(coro, *, name):
        coro.close()

    with patch.object(background_task_watchdog, "create_task", side_effect=close_background_coro):
        await service.close_trade(
            signal_id,
            exit_prices={"AAPL": 151.0},
            pnl=1.25,
            exit_reason=ExitReason.TAKE_PROFIT,
        )

    ensure.assert_awaited_once()
    assert ensure.await_args.args[0] == signal_id
    assert ensure.await_args.args[1] == ExitReason.TAKE_PROFIT
    assert ensure.await_args.kwargs["session"] is fake_session


@pytest.mark.asyncio
async def test_ensure_journal_exit_reason_conflict_only_sets_exit(monkeypatch):
    signal_id = uuid.uuid4()
    captured: dict = {}

    class _Session:
        async def execute(self, stmt):
            captured["stmt"] = stmt

    session = _Session()
    service = PersistenceService()

    await service.ensure_journal_exit_reason(
        signal_id,
        ExitReason.STOP_LOSS,
        session=session,  # type: ignore[arg-type]
        entry_regime=MarketRegime.STABLE,
    )

    stmt = captured["stmt"]
    # Dialect insert ... ON CONFLICT DO UPDATE SET exit_reason=...
    sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "exit_reason" in sql.lower() or hasattr(stmt, "_post_values_clause")
    # Ensure we did not ask to overwrite reflection_text on conflict.
    set_ = getattr(getattr(stmt, "_post_values_clause", None), "update_values_to_set", None)
    if set_ is None:
        # Fallback: inspect bound parameters / string form of on_conflict clause
        conflict = getattr(stmt, "_post_values_clause", None)
        assert conflict is not None
        conflict_sql = str(conflict).lower()
        assert "exit_reason" in conflict_sql
        assert "reflection_text" not in conflict_sql
    else:
        keys = {str(k) for k in set_}
        assert any("exit_reason" in k for k in keys)
        assert not any("reflection_text" in k for k in keys)


@pytest.mark.asyncio
async def test_audit_journal_vs_ledger_reports_and_repairs(monkeypatch):
    signal_missing = uuid.uuid4()
    signal_no_exit = uuid.uuid4()
    signal_ok = uuid.uuid4()

    ledger_rows = [
        (signal_missing, {"exit_reason": ExitReason.TAKE_PROFIT.value, "pnl": 1.0}),
        (signal_no_exit, {"exit_reason": ExitReason.STOP_LOSS.value, "pnl": -1.0}),
        (signal_ok, {"exit_reason": ExitReason.MANUAL.value, "pnl": 0.0}),
    ]
    journals = [
        SimpleNamespace(signal_id=signal_no_exit, exit_reason=None),
        SimpleNamespace(signal_id=signal_ok, exit_reason=ExitReason.MANUAL),
    ]

    class _Scalar:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Result:
        def __init__(self, rows, *, scalars=False):
            self._rows = rows
            self._scalars = scalars

        def all(self):
            return self._rows

        def scalars(self):
            return _Scalar(self._rows)

    class _Session:
        def __init__(self):
            self.committed = False
            self._n = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, _stmt):
            self._n += 1
            if self._n == 1:
                return _Result(ledger_rows)
            return _Result(journals, scalars=True)

        async def commit(self):
            self.committed = True

    session = _Session()
    monkeypatch.setattr(
        "src.services.journal_audit_service.persistence_service.AsyncSessionLocal",
        lambda: session,
    )
    ensure = AsyncMock()
    monkeypatch.setattr(
        "src.services.journal_audit_service.persistence_service.ensure_journal_exit_reason",
        ensure,
    )

    dry = await audit_journal_vs_ledger(repair=False)
    assert signal_missing.hex in "".join(dry["missing_journal"]).replace("-", "") or str(signal_missing) in dry["missing_journal"]
    assert str(signal_missing) in dry["missing_journal"]
    assert str(signal_no_exit) in dry["missing_exit_reason"]
    assert dry["repaired"] == 0
    ensure.assert_not_awaited()

    session2 = _Session()
    monkeypatch.setattr(
        "src.services.journal_audit_service.persistence_service.AsyncSessionLocal",
        lambda: session2,
    )
    repaired = await audit_journal_vs_ledger(repair=True)
    assert repaired["repaired"] == 2
    assert session2.committed is True
    assert ensure.await_count == 2


@pytest.mark.asyncio
async def test_auto_reconcile_confirmed_closes_stamps_journal(monkeypatch):
    from src.services.ledger_reconcile_service import auto_reconcile_broker_confirmed_closes

    signal_id = str(uuid.uuid4())

    class _ScalarRows:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _ExecuteResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _ScalarRows(self._rows)

    class _FakeSession:
        def __init__(self, rows):
            self._rows = rows
            self.added = []
            self.committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, _statement):
            return _ExecuteResult(self._rows)

        def add(self, row):
            self.added.append(row)

        async def commit(self):
            self.committed = True

    rows = [
        SimpleNamespace(
            id=str(uuid.uuid4()),
            signal_id=signal_id,
            ticker="ETH-USD",
            status=OrderStatus.CLOSE_FAILED,
            closed_at=None,
            metadata_json={},
        ),
        SimpleNamespace(
            id=str(uuid.uuid4()),
            signal_id=signal_id,
            ticker="BTC-USD",
            status=OrderStatus.CLOSE_FAILED,
            closed_at=None,
            metadata_json={},
        ),
    ]
    session = _FakeSession(rows)
    monkeypatch.setattr(
        "src.services.ledger_reconcile_service.persistence_service.AsyncSessionLocal",
        lambda: session,
    )
    stamp = AsyncMock()
    monkeypatch.setattr(
        "src.services.ledger_reconcile_service._stamp_journal_exit_for_signal",
        stamp,
    )

    async def _get_by_cid(client_order_id: str):
        return {
            "id": f"broker-{client_order_id}",
            "status": "filled",
            "filled_qty": 0.01,
            "filled_avg_price": 100.0,
        }

    brokerage = SimpleNamespace(get_order_by_client_order_id=AsyncMock(side_effect=_get_by_cid))
    summary = await auto_reconcile_broker_confirmed_closes(brokerage=brokerage, dry_run=False)

    assert summary["closed"] == 1
    stamp.assert_awaited_once()
    assert stamp.await_args.args[1] == signal_id
    assert all(row.metadata_json.get("exit_reason") == ExitReason.MANUAL.value for row in rows)
