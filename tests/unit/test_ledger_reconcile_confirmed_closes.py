from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from src.services.ledger_reconcile_service import auto_reconcile_broker_confirmed_closes
from src.services.persistence_service import OrderStatus


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


def _leg(signal_id, ticker, status=OrderStatus.CLOSE_FAILED):
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        signal_id=signal_id,
        ticker=ticker,
        status=status,
        closed_at=None,
        metadata_json={},
    )


@pytest.mark.asyncio
async def test_auto_reconcile_broker_confirmed_closes_closes_filled_pair(monkeypatch):
    signal_id = str(uuid.uuid4())
    rows = [
        _leg(signal_id, "ETH-USD"),
        _leg(signal_id, "BTC-USD"),
    ]
    session = _FakeSession(rows)

    class _SessionFactory:
        def __call__(self):
            return session

    monkeypatch.setattr(
        "src.services.ledger_reconcile_service.persistence_service.AsyncSessionLocal",
        _SessionFactory(),
    )

    async def _get_by_cid(client_order_id: str):
        assert client_order_id.endswith(("-CLOSE-ETH-USD", "-CLOSE-BTC-USD"))
        return {
            "id": f"broker-{client_order_id}",
            "status": "filled",
            "filled_qty": 0.01,
            "filled_avg_price": 100.0,
        }

    brokerage = SimpleNamespace(get_order_by_client_order_id=AsyncMock(side_effect=_get_by_cid))

    summary = await auto_reconcile_broker_confirmed_closes(brokerage=brokerage, dry_run=False)

    assert summary["closed"] == 1
    assert summary["signals_examined"] == 1
    assert session.committed is True
    assert all(row.status == OrderStatus.CLOSED for row in rows)
    assert all(row.closed_at is not None for row in rows)


@pytest.mark.asyncio
async def test_auto_reconcile_broker_confirmed_closes_skips_missing_close_order(monkeypatch):
    signal_id = str(uuid.uuid4())
    rows = [
        _leg(signal_id, "ETH-USD"),
        _leg(signal_id, "BTC-USD"),
    ]
    session = _FakeSession(rows)

    class _SessionFactory:
        def __call__(self):
            return session

    monkeypatch.setattr(
        "src.services.ledger_reconcile_service.persistence_service.AsyncSessionLocal",
        _SessionFactory(),
    )

    async def _get_by_cid(client_order_id: str):
        if client_order_id.endswith("ETH-USD"):
            return {"id": "eth-close", "status": "filled", "filled_qty": 0.01}
        raise LookupError("not found")

    brokerage = SimpleNamespace(get_order_by_client_order_id=AsyncMock(side_effect=_get_by_cid))

    summary = await auto_reconcile_broker_confirmed_closes(brokerage=brokerage, dry_run=False)

    assert summary["closed"] == 0
    assert summary["blocked"] == 2
    assert session.committed is False
    assert all(row.status == OrderStatus.CLOSE_FAILED for row in rows)
