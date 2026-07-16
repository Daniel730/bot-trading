import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.services.ledger_reconcile_service import (
    SignalReconciliationAction,
    auto_close_flat_orphans,
    classify_signal_reconciliation,
    is_flat_orphan_candidate,
    plan_signal_level_reconciliation,
)
from src.services.persistence_service import OrderSide, OrderStatus


def _row(
    *,
    ledger_id: str = "row-1",
    order_id: str = "order-1",
    signal_id: str = "signal-1",
    ticker: str = "BTC-USD",
    side: OrderSide = OrderSide.BUY,
    quantity: float = 0.01,
    price: float = 50000.0,
    status: OrderStatus = OrderStatus.NEEDS_MANUAL_RECONCILIATION,
):
    return SimpleNamespace(
        id=ledger_id,
        order_id=order_id,
        signal_id=signal_id,
        ticker=ticker,
        side=side,
        quantity=quantity,
        price=price,
        status=status,
        metadata_json={},
        closed_at=None,
    )


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


def test_classify_safe_auto_close_when_broker_flat():
    rows = [
        _row(ticker="ETH-USD", side=OrderSide.SELL, ledger_id="eth", order_id="eth-order"),
        _row(ticker="BTC-USD", side=OrderSide.BUY, ledger_id="btc", order_id="btc-order"),
    ]
    plan = classify_signal_reconciliation(
        signal_id="signal-1",
        rows=rows,
        positions=[],
        pending_orders=[],
        order_snapshots={},
        order_snapshot_errors={},
        managed_open_tickers={},
    )
    assert plan.action == SignalReconciliationAction.SAFE_AUTO_CLOSE
    assert plan.reasons == ["broker_flat_no_open_orders"]


def test_classify_safe_auto_restore_open_for_filled_pair_with_positions():
    rows = [
        _row(
            ticker="ETH-USD",
            side=OrderSide.SELL,
            ledger_id="eth",
            order_id="eth-order",
            quantity=0.5,
            price=3000.0,
        ),
        _row(
            ticker="BTC-USD",
            side=OrderSide.BUY,
            ledger_id="btc",
            order_id="btc-order",
            quantity=0.01,
            price=50000.0,
        ),
    ]
    plan = classify_signal_reconciliation(
        signal_id="signal-1",
        rows=rows,
        positions=[
            {"ticker": "ETH-USD", "quantity": -0.5},
            {"ticker": "BTC-USD", "quantity": 0.01},
        ],
        pending_orders=[],
        order_snapshots={
            "eth-order": {
                "status": "filled",
                "filled_qty": 0.5,
                "filled_avg_price": 3000.0,
            },
            "btc-order": {
                "status": "filled",
                "filled_qty": 0.01,
                "filled_avg_price": 50000.0,
            },
        },
        order_snapshot_errors={"eth-order": None, "btc-order": None},
        managed_open_tickers={},
    )
    assert plan.action == SignalReconciliationAction.SAFE_AUTO_RESTORE_OPEN
    assert plan.reasons == ["both_legs_filled_positions_match"]


def test_classify_manual_required_when_pending_orders_exist():
    rows = [_row()]
    plan = classify_signal_reconciliation(
        signal_id="signal-1",
        rows=rows,
        positions=[{"ticker": "BTC-USD", "quantity": 0.01}],
        pending_orders=[{"id": "order-1", "ticker": "BTC-USD", "status": "new"}],
        order_snapshots={
            "order-1": {"status": "filled", "filled_qty": 0.01, "filled_avg_price": 50000.0}
        },
        order_snapshot_errors={"order-1": None},
        managed_open_tickers={},
    )
    assert plan.action == SignalReconciliationAction.MANUAL_REQUIRED
    assert "pending_orders_present" in plan.reasons


def test_classify_manual_required_on_symbol_collision():
    rows = [_row(ticker="BTC-USD")]
    plan = classify_signal_reconciliation(
        signal_id="signal-1",
        rows=rows,
        positions=[{"ticker": "BTC-USD", "quantity": 0.01}],
        pending_orders=[],
        order_snapshots={
            "order-1": {"status": "filled", "filled_qty": 0.01, "filled_avg_price": 50000.0}
        },
        order_snapshot_errors={"order-1": None},
        managed_open_tickers={"BTC-USD": {"other-signal"}},
    )
    assert plan.action == SignalReconciliationAction.MANUAL_REQUIRED
    assert any("symbol_collision" in reason for reason in plan.reasons)


def test_classify_manual_required_when_order_snapshot_missing():
    rows = [_row(), _row(ticker="ETH-USD", side=OrderSide.SELL, order_id="eth-order", ledger_id="eth")]
    plan = classify_signal_reconciliation(
        signal_id="signal-1",
        rows=rows,
        positions=[
            {"ticker": "BTC-USD", "quantity": 0.01},
            {"ticker": "ETH-USD", "quantity": -0.5},
        ],
        pending_orders=[],
        order_snapshots={"order-1": None},
        order_snapshot_errors={"order-1": "404 not found", "eth-order": None},
        managed_open_tickers={},
    )
    assert plan.action == SignalReconciliationAction.MANUAL_REQUIRED
    assert any("snapshot" in reason for reason in plan.reasons)


@pytest.mark.asyncio
async def test_plan_signal_level_reconciliation_groups_rows(monkeypatch):
    eth_row = _row(
        ticker="ETH-USD",
        side=OrderSide.SELL,
        ledger_id="eth",
        order_id="eth-order",
        quantity=0.5,
    )
    btc_row = _row(
        ticker="BTC-USD",
        side=OrderSide.BUY,
        ledger_id="btc",
        order_id="btc-order",
        quantity=0.01,
    )

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[eth_row, btc_row]))
            )
        )
    )

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
    monkeypatch.setattr(
        "src.services.ledger_reconcile_service.persistence_service.get_open_signals",
        AsyncMock(return_value=[]),
    )

    brokerage = MagicMock()
    brokerage.get_portfolio = AsyncMock(
        return_value=[
            {"ticker": "ETH-USD", "quantity": -0.5},
            {"ticker": "BTC-USD", "quantity": 0.01},
        ]
    )
    brokerage.get_pending_orders = AsyncMock(return_value=[])
    brokerage.get_order = AsyncMock(
        side_effect=lambda order_id: {
            "eth-order": {
                "status": "filled",
                "filled_qty": 0.5,
                "filled_avg_price": 3000.0,
            },
            "btc-order": {
                "status": "filled",
                "filled_qty": 0.01,
                "filled_avg_price": 50000.0,
            },
        }[order_id]
    )

    result = await plan_signal_level_reconciliation(brokerage=brokerage)
    assert result["examined_rows"] == 2
    assert result["signal_count"] == 1
    assert result["summary"][SignalReconciliationAction.SAFE_AUTO_RESTORE_OPEN.value] == 1
    assert result["plans"][0].action == SignalReconciliationAction.SAFE_AUTO_RESTORE_OPEN
