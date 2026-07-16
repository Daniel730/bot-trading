import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.services.ledger_reconcile_service import auto_reconcile_broker_confirmed_pairs
from src.services.persistence_service import OrderStatus


def _leg(signal_id, ticker, order_id, qty, status=OrderStatus.NEEDS_MANUAL_RECONCILIATION):
    return SimpleNamespace(
        id=f"leg-{ticker}",
        signal_id=signal_id,
        order_id=order_id,
        ticker=ticker,
        quantity=qty,
        price=100.0,
        status=status,
        metadata_json={"filled_qty": qty, "broker_order_id": order_id},
        closed_at=None,
    )


@pytest.mark.asyncio
async def test_auto_reconcile_broker_confirmed_pairs_restores_open_pair(monkeypatch):
    signal_id = "signal-1"
    legs = [
        _leg(signal_id, "BTC-USD", "order-a", 0.001),
        _leg(signal_id, "ETH-USD", "order-b", 0.02),
    ]

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=legs))))
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
        lambda: (OrderStatus.NEEDS_MANUAL_RECONCILIATION,),
    )

    brokerage = MagicMock()
    brokerage.get_order = AsyncMock(
        side_effect=[
            {"status": "filled", "filled_qty": 0.001, "filled_avg_price": 65000.0},
            {"status": "filled", "filled_qty": 0.02, "filled_avg_price": 1900.0},
        ]
    )

    summary = await auto_reconcile_broker_confirmed_pairs(brokerage=brokerage, dry_run=False)
    assert summary["restored"] == 2
    assert summary["blocked"] == 0
    assert all(leg.status == OrderStatus.OPEN_PAIR for leg in legs)
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_auto_reconcile_broker_confirmed_pairs_blocks_non_filled(monkeypatch):
    signal_id = "signal-2"
    legs = [
        _leg(signal_id, "BTC-USD", "order-a", 0.001),
        _leg(signal_id, "ETH-USD", "order-b", 0.02),
    ]

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=legs))))
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
        lambda: (OrderStatus.NEEDS_MANUAL_RECONCILIATION,),
    )

    brokerage = MagicMock()
    brokerage.get_order = AsyncMock(
        side_effect=[
            {"status": "filled", "filled_qty": 0.001, "filled_avg_price": 65000.0},
            {"status": "new", "filled_qty": 0.0, "filled_avg_price": 0.0},
        ]
    )

    summary = await auto_reconcile_broker_confirmed_pairs(brokerage=brokerage, dry_run=False)
    assert summary["restored"] == 0
    assert summary["blocked"] == 2
    assert legs[0].status == OrderStatus.NEEDS_MANUAL_RECONCILIATION
    session.commit.assert_not_awaited()
