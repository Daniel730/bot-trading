from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import reconcile_orphans
from src.services.persistence_service import OrderSide, OrderStatus


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


class _FakeBrokerage:
    def __init__(self):
        self.get_portfolio = AsyncMock(
            return_value=[
                {
                    "ticker": "BTC-USD",
                    "quantityAvailableForTrading": 0.004198,
                }
            ]
        )
        self.get_pending_orders = AsyncMock(
            return_value=[
                {
                    "id": "ORPHAN_abc",
                    "ticker": "BTC-USD",
                    "status": "accepted",
                }
            ]
        )


@pytest.mark.asyncio
async def test_reconcile_orphans_live_mode_reports_broker_state_without_mutating(monkeypatch, caplog):
    caplog.set_level("INFO", logger="reconcile_orphans")
    row = SimpleNamespace(
        id="ledger-1",
        signal_id="signal-1",
        order_id="ORPHAN_abc",
        ticker="BTC-USD",
        side=OrderSide.BUY,
        quantity=0.004198,
        status=OrderStatus.FAILED,
        venue="ALPACA",
        closed_at=None,
        metadata_json=None,
    )
    fake_session = _FakeSession([row])
    fake_brokerage = _FakeBrokerage()
    monkeypatch.setattr(
        reconcile_orphans.persistence_service,
        "AsyncSessionLocal",
        lambda: fake_session,
    )
    monkeypatch.setattr(
        reconcile_orphans,
        "BrokerageService",
        lambda: fake_brokerage,
    )

    exit_code = await reconcile_orphans.reconcile_orphans(dry_run=False)

    assert exit_code == 2
    assert row.closed_at is None
    assert row.status is OrderStatus.FAILED
    assert row.metadata_json is None
    assert fake_session.added == []
    assert fake_session.committed is False
    fake_brokerage.get_portfolio.assert_awaited_once()
    fake_brokerage.get_pending_orders.assert_awaited_once()
    assert "broker_qty=0.004198" in caplog.text
    assert "open_order_ids=['ORPHAN_abc']" in caplog.text
    assert "--live is disabled" in caplog.text
