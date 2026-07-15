import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.services.ledger_reconcile_service import (
    auto_close_flat_orphans,
    is_flat_orphan_candidate,
)
from src.services.persistence_service import OrderStatus


def test_is_flat_orphan_candidate_for_orphan_prefix_and_failed_status():
    orphan = SimpleNamespace(
        order_id="ORPHAN_abc",
        status=OrderStatus.LEG_A_SUBMITTED,
        metadata_json={},
    )
    failed = SimpleNamespace(
        order_id="normal-id",
        status=OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
        metadata_json={},
    )
    open_pair = SimpleNamespace(
        order_id="pair-1",
        status=OrderStatus.OPEN_PAIR,
        metadata_json={},
    )
    assert is_flat_orphan_candidate(orphan) is True
    assert is_flat_orphan_candidate(failed) is True
    assert is_flat_orphan_candidate(open_pair) is False


@pytest.mark.asyncio
async def test_auto_close_flat_orphans_closes_when_broker_flat(monkeypatch):
    row = SimpleNamespace(
        id="row-1",
        order_id="ORPHAN_xyz",
        ticker="BTC-USD",
        status=OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
        metadata_json={"orphaned": True},
        closed_at=None,
    )

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row]))))
    )
    session.add = MagicMock()
    session.commit = AsyncMock()

    class _CM:
        def __call__(self):
            return session

    monkeypatch.setattr(
        "src.services.ledger_reconcile_service.persistence_service.AsyncSessionLocal",
        _CM(),
    )
    monkeypatch.setattr(
        "src.services.ledger_reconcile_service.persistence_service._startup_unresolved_statuses",
        lambda: (
            OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
            OrderStatus.NEEDS_MANUAL_RECONCILIATION,
        ),
    )

    brokerage = MagicMock()
    brokerage.get_portfolio = AsyncMock(return_value=[])
    brokerage.get_pending_orders = AsyncMock(return_value=[])

    summary = await auto_close_flat_orphans(brokerage=brokerage, dry_run=False)
    assert summary["closed"] == 1
    assert summary["blocked"] == 0
    assert row.status == OrderStatus.CLOSED
    assert row.closed_at is not None
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_auto_close_flat_orphans_blocks_when_broker_holds_position(monkeypatch):
    row = SimpleNamespace(
        id="row-2",
        order_id="ORPHAN_xyz",
        ticker="BTC-USD",
        status=OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,
        metadata_json={"orphaned": True},
        closed_at=None,
    )

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row]))))
    )
    session.commit = AsyncMock()

    class _CM:
        def __call__(self):
            return session

    monkeypatch.setattr(
        "src.services.ledger_reconcile_service.persistence_service.AsyncSessionLocal",
        _CM(),
    )
    monkeypatch.setattr(
        "src.services.ledger_reconcile_service.persistence_service._startup_unresolved_statuses",
        lambda: (OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION,),
    )

    brokerage = MagicMock()
    brokerage.get_portfolio = AsyncMock(
        return_value=[{"ticker": "BTC-USD", "quantity": 0.18, "marketValue": 11000}]
    )
    brokerage.get_pending_orders = AsyncMock(return_value=[])

    summary = await auto_close_flat_orphans(brokerage=brokerage, dry_run=False)
    assert summary["closed"] == 0
    assert summary["blocked"] == 1
    assert row.status == OrderStatus.FAILED_REQUIRES_MANUAL_RECONCILIATION
    session.commit.assert_not_awaited()
