"""Partial-fill ledger completeness via update_trade_fill (PR D)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.persistence_service import OrderStatus, PersistenceService


@pytest.mark.asyncio
async def test_update_trade_fill_persists_qty_avg_remaining(monkeypatch):
    service = PersistenceService()
    signal_id = uuid.uuid4()
    order_id = "ord-a"
    row_id = 1

    existing = MagicMock()
    existing.id = row_id
    existing.metadata_json = {"submitted_qty": 10.0}
    existing.quantity = 10.0

    session = MagicMock()
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=session)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = begin_cm

    select_result = MagicMock()
    select_result.all.return_value = [existing]
    session.execute = AsyncMock(return_value=select_result)

    monkeypatch.setattr(service, "AsyncSessionLocal", lambda: session_cm)

    await service.update_trade_fill(
        signal_id,
        order_id,
        filled_quantity=4.0,
        fill_price=151.25,
        status=OrderStatus.PARTIAL_EXPOSURE,
        expected_quantity=10.0,
        fee=0.0,
        metadata_updates={"pair_status": "PARTIAL_EXPOSURE"},
    )

    assert session.execute.await_count >= 2
    update_call = session.execute.await_args_list[-1]
    stmt = update_call.args[0]
    raw_values = getattr(stmt, "_values", {}) or {}
    meta = None
    qty = None
    for col, val in raw_values.items():
        candidate = getattr(val, "value", val)
        key = getattr(col, "key", str(col))
        if key in ("metadata_json", "metadata") or isinstance(candidate, dict):
            if isinstance(candidate, dict):
                meta = candidate
        if key == "quantity":
            qty = candidate
    assert qty == 4.0
    assert isinstance(meta, dict)
    assert meta["filled_qty"] == 4.0
    assert meta["filled_avg_price"] == 151.25
    assert meta["expected_qty"] == 10.0
    assert meta["remaining_qty"] == 6.0
    assert meta["pair_status"] == "PARTIAL_EXPOSURE"


@pytest.mark.asyncio
async def test_get_open_signals_exposes_partial_fill_fields(monkeypatch):
    service = PersistenceService()
    signal_id = uuid.uuid4()

    trade = MagicMock()
    trade.signal_id = signal_id
    trade.ticker = "AAPL"
    trade.side = MagicMock(value="BUY")
    trade.quantity = 4.0
    trade.price = 151.25
    trade.fee = 0.0
    trade.execution_timestamp = None
    trade.venue = "ALPACA"
    trade.is_shadow = False
    trade.execution_lane = "BROKER"
    trade.status = OrderStatus.PARTIAL_EXPOSURE
    trade.order_id = "ord-a"
    trade.metadata_json = {
        "filled_qty": 4.0,
        "filled_avg_price": 151.25,
        "expected_qty": 10.0,
        "remaining_qty": 6.0,
        "slippage_bps": 0,
    }

    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [trade]
    session.execute = AsyncMock(return_value=result)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(service, "AsyncSessionLocal", lambda: session_cm)

    signals = await service.get_open_signals()
    assert len(signals) == 1
    leg = signals[0]["legs"][0]
    assert leg["filled_avg_price"] == 151.25
    assert leg["expected_qty"] == 10.0
    assert leg["remaining_qty"] == 6.0
    assert leg["filled_qty"] == 4.0
    assert leg["order_id"] == "ord-a"
