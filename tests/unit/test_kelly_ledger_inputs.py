"""Kelly inputs from closed-ledger PnL (PR E)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.persistence_service import OrderStatus, PersistenceService, TradeLedger


def _closed_leg(*, signal_id, pnl: float):
    row = MagicMock(spec=TradeLedger)
    row.id = uuid.uuid4()
    row.signal_id = signal_id
    row.status = OrderStatus.CLOSED
    row.metadata_json = {"pnl": pnl}
    return row


@pytest.mark.asyncio
async def test_kelly_inputs_fall_back_to_defaults_below_min_trades(monkeypatch):
    service = PersistenceService()
    sig = uuid.uuid4()
    rows = [_closed_leg(signal_id=sig, pnl=10.0), _closed_leg(signal_id=sig, pnl=10.0)]

    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(service, "AsyncSessionLocal", lambda: session_cm)
    monkeypatch.setattr(
        "src.services.persistence_service.settings",
        SimpleNamespace(
            DEFAULT_WIN_PROBABILITY=0.55,
            DEFAULT_WIN_LOSS_RATIO=1.0,
            KELLY_LEDGER_MIN_TRADES=20,
        ),
    )

    out = await service.get_kelly_inputs_from_ledger(min_trades=5)
    assert out["source"] == "defaults"
    assert out["win_prob"] == 0.55
    assert out["closed_trades"] == 1


@pytest.mark.asyncio
async def test_kelly_inputs_from_ledger_when_sample_large_enough(monkeypatch):
    service = PersistenceService()
    wins = [uuid.uuid4() for _ in range(6)]
    losses = [uuid.uuid4() for _ in range(4)]
    rows = [_closed_leg(signal_id=s, pnl=20.0) for s in wins] + [
        _closed_leg(signal_id=s, pnl=-10.0) for s in losses
    ]

    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(service, "AsyncSessionLocal", lambda: session_cm)
    monkeypatch.setattr(
        "src.services.persistence_service.settings",
        SimpleNamespace(
            DEFAULT_WIN_PROBABILITY=0.55,
            DEFAULT_WIN_LOSS_RATIO=1.0,
            KELLY_LEDGER_MIN_TRADES=5,
        ),
    )

    out = await service.get_kelly_inputs_from_ledger(min_trades=5)
    assert out["source"] == "ledger"
    assert out["closed_trades"] == 10
    assert out["win_prob"] == pytest.approx(0.6)
    # avg win 20 / avg loss 10
    assert out["win_loss_ratio"] == pytest.approx(2.0)
