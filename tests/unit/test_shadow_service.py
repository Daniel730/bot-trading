"""Shadow lane ledger continuity: signal_id reuse + atomic pair-leg writes."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.persistence_service import OrderSide, OrderStatus, PersistenceService
from src.services.shadow_service import ShadowService, apply_shadow_fill_slippage


@pytest.mark.asyncio
async def test_execute_simulated_trade_reuses_signal_id_and_logs_atomically(monkeypatch):
    service = ShadowService()
    captured: list[list[dict]] = []

    async def fake_log_trades(rows):
        captured.append(rows)

    monkeypatch.setattr(
        "src.services.shadow_service.persistence_service.log_trades",
        fake_log_trades,
    )

    signal_id = str(uuid.uuid4())
    returned = await service.execute_simulated_trade(
        "ETH-USD_SOL-USD",
        "Short-Long",
        1.0,
        8.9,
        3000.0,
        140.0,
        signal_id=signal_id,
    )

    assert returned == uuid.UUID(signal_id)
    assert len(captured) == 1
    legs = captured[0]
    assert len(legs) == 2
    assert legs[0]["signal_id"] == uuid.UUID(signal_id)
    assert legs[1]["signal_id"] == uuid.UUID(signal_id)
    assert legs[0]["ticker"] == "ETH-USD"
    assert legs[1]["ticker"] == "SOL-USD"
    assert legs[0]["side"] == OrderSide.SELL
    assert legs[1]["side"] == OrderSide.BUY
    assert legs[0]["status"] == OrderStatus.OPEN
    assert legs[0]["metadata_json"]["is_shadow"] is True
    assert legs[0]["metadata_json"]["execution_lane"] == "SHADOW"
    # Fill price embeds adverse slip; audit key must not be slippage_bps (PnL double-count).
    assert "slippage_bps" not in legs[0]["metadata_json"]
    assert legs[0]["metadata_json"]["applied_slippage_bps"] > 0
    # Short-Long: leg A SELL → fill below mid; leg B BUY → fill above mid
    assert legs[0]["price"] < 3000.0
    assert legs[1]["price"] > 140.0


def test_apply_shadow_fill_slippage_buy_pays_up_sell_receives_less():
    buy_px, bps = apply_shadow_fill_slippage(100.0, "BUY", slippage_bps=10.0)
    sell_px, _ = apply_shadow_fill_slippage(100.0, "SELL", slippage_bps=10.0)
    assert bps == 10.0
    assert buy_px == pytest.approx(100.1)
    assert sell_px == pytest.approx(99.9)


@pytest.mark.asyncio
async def test_close_simulated_trade_returns_slipped_exits(monkeypatch):
    service = ShadowService()
    monkeypatch.setattr(
        "src.services.shadow_service.settings",
        SimpleNamespace(FLAT_ORDER_FRICTION_USD=0.0, SHADOW_FILL_SLIPPAGE_BPS=10.0),
    )
    monkeypatch.setattr(
        "src.services.shadow_service.apply_shadow_fill_slippage",
        lambda mid, side, slippage_bps=None: (
            (mid * 1.001, 10.0) if str(side).upper() == "BUY" else (mid * 0.999, 10.0)
        ),
    )
    total, exit_a, exit_b = await service.close_simulated_trade(
        "AAPL_MSFT",
        uuid.uuid4(),
        "Long-Short",
        10.0,
        5.0,
        150.0,
        300.0,
        160.0,
        290.0,
    )
    # Long-Short close: SELL A / BUY B
    assert exit_a == pytest.approx(160.0 * 0.999)
    assert exit_b == pytest.approx(290.0 * 1.001)
    assert isinstance(total, float)


@pytest.mark.asyncio
async def test_log_trades_commits_both_legs_in_one_transaction(monkeypatch):
    added: list = []

    session = MagicMock()
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=session)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = begin_cm
    session.add.side_effect = lambda trade: added.append(trade)

    service = PersistenceService()
    monkeypatch.setattr(service, "AsyncSessionLocal", lambda: session_cm)
    monkeypatch.setattr(
        "src.services.persistence_service.settings",
        SimpleNamespace(execution_lane="SHADOW", is_broker_paper_trading=False),
    )

    signal_id = uuid.uuid4()
    await service.log_trades(
        [
            {
                "order_id": "a",
                "signal_id": signal_id,
                "ticker": "ETH-USD",
                "side": OrderSide.SELL,
                "quantity": 1.0,
                "price": 3000.0,
                "status": OrderStatus.OPEN,
                "metadata_json": {"is_shadow": True, "execution_lane": "SHADOW"},
            },
            {
                "order_id": "b",
                "signal_id": signal_id,
                "ticker": "SOL-USD",
                "side": OrderSide.BUY,
                "quantity": 8.9,
                "price": 140.0,
                "status": OrderStatus.OPEN,
                "metadata_json": {"is_shadow": True, "execution_lane": "SHADOW"},
            },
        ]
    )

    assert session.begin.call_count == 1
    assert len(added) == 2
    assert {row.ticker for row in added} == {"ETH-USD", "SOL-USD"}
    assert all(row.signal_id == signal_id for row in added)
    assert all(row.is_shadow is True for row in added)
