"""Orphan close must not flatten ledger on Alpaca submit-accept (status=success)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.services.leg_orphan_recovery import recover_leg_a_orphans
from src.services.persistence_service import OrderSide, OrderStatus


class _Begin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _Session:
    def __init__(self, rows):
        self._rows = rows
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        return _Begin()

    async def execute(self, _stmt):
        result = MagicMock()
        result.scalars.return_value.all.return_value = list(self._rows)
        return result

    def add(self, row):
        self.added.append(row)


@pytest.mark.asyncio
async def test_orphan_recovery_success_status_marks_needs_manual_not_closed(monkeypatch):
    sid = uuid4()
    row = SimpleNamespace(
        id=uuid4(),
        order_id=f"{sid}-A",
        signal_id=sid,
        ticker="ORPHAN1",
        side=OrderSide.BUY,
        quantity=2.0,
        price=10.0,
        status=OrderStatus.LEG_A_FILLED,
        closed_at=None,
        metadata_json={"orphaned_candidate": True},
    )
    session = _Session([row])

    persistence = SimpleNamespace(
        AsyncSessionLocal=lambda: session,
        update_signal_status=AsyncMock(),
    )
    monkeypatch.setattr(
        "src.services.leg_orphan_recovery.persistence_service",
        persistence,
    )

    placed = []

    class FakeBroker:
        async def get_portfolio(self):
            return [{"ticker": "ORPHAN1", "quantity": 2.0}]

        async def get_pending_orders(self):
            return []

        async def place_market_order(
            self, ticker, qty, side, limit_price=None, client_order_id=None, *, intent="open"
        ):
            placed.append({"ticker": ticker, "qty": qty, "side": side, "intent": intent})
            return {"status": "success", "order_id": "close-1"}

    summary = await recover_leg_a_orphans(brokerage=FakeBroker(), dry_run=False)
    assert summary["recovered"] == 0
    assert summary["skipped"] >= 1
    assert placed
    persistence.update_signal_status.assert_awaited()
    status_arg = persistence.update_signal_status.await_args.args[1]
    assert status_arg == OrderStatus.NEEDS_MANUAL_RECONCILIATION
    assert row.closed_at is None
    assert row.status == OrderStatus.LEG_A_FILLED  # row flatten skipped


@pytest.mark.asyncio
async def test_orphan_recovery_filled_status_flattens_ledger(monkeypatch):
    sid = uuid4()
    row = SimpleNamespace(
        id=uuid4(),
        order_id=f"{sid}-A",
        signal_id=sid,
        ticker="ORPHAN2",
        side=OrderSide.BUY,
        quantity=2.0,
        price=10.0,
        status=OrderStatus.LEG_A_FILLED,
        closed_at=None,
        metadata_json={"orphaned_candidate": True},
    )
    session = _Session([row])

    persistence = SimpleNamespace(
        AsyncSessionLocal=lambda: session,
        update_signal_status=AsyncMock(),
    )
    monkeypatch.setattr(
        "src.services.leg_orphan_recovery.persistence_service",
        persistence,
    )

    class FakeBroker:
        async def get_portfolio(self):
            return [{"ticker": "ORPHAN2", "quantity": 2.0}]

        async def get_pending_orders(self):
            return []

        async def place_market_order(
            self, ticker, qty, side, limit_price=None, client_order_id=None, *, intent="open"
        ):
            return {"status": "filled", "order_id": "close-2"}

    summary = await recover_leg_a_orphans(brokerage=FakeBroker(), dry_run=False)
    assert summary["recovered"] >= 1
    status_arg = persistence.update_signal_status.await_args.args[1]
    assert status_arg == OrderStatus.CLOSED
    assert row.status == OrderStatus.CLOSED
    assert isinstance(row.closed_at, datetime)
    assert row.closed_at.tzinfo == timezone.utc
