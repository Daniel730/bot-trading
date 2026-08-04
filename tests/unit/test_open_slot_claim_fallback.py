"""Open-slot claim fallback policy (no Postgres required)."""

from __future__ import annotations

import pytest

from src.config import settings
from src.services.open_slot_reservation import OpenSlotReservationService, TradeIntentWAL


@pytest.mark.asyncio
async def test_claim_falls_back_local_when_distributed_down_on_paper(tmp_path, monkeypatch):
    """Paper/auto-approve: Postgres claim errors fall back to local+WAL (not skip trades)."""
    monkeypatch.setattr(settings, "PAPER_TRADING", True)

    class _BrokenDist:
        async def claim(self, **_kwargs):
            raise RuntimeError("Event loop is closed")

    wal = TradeIntentWAL(path=tmp_path / "paper.wal")
    svc = OpenSlotReservationService(wal=wal, distributed=_BrokenDist(), ttl_seconds=120)
    result = await svc.claim(
        signal_id="paper-fallback-1",
        ticker_a="AAPL",
        ticker_b="MSFT",
        open_signals=[],
        max_open_pairs=8,
        block_shared_legs=True,
    )
    assert result.get("ok") is True
    assert svc.has("paper-fallback-1")


@pytest.mark.asyncio
async def test_claim_fails_closed_when_distributed_down_on_live(tmp_path, monkeypatch):
    """Real-money LIVE: Postgres claim errors refuse the claim (fail-closed)."""
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(
        OpenSlotReservationService,
        "_allows_local_claim_fallback",
        staticmethod(lambda: False),
    )

    class _BrokenDist:
        async def claim(self, **_kwargs):
            raise RuntimeError("Event loop is closed")

    wal = TradeIntentWAL(path=tmp_path / "live.wal")
    svc = OpenSlotReservationService(wal=wal, distributed=_BrokenDist(), ttl_seconds=120)
    result = await svc.claim(
        signal_id="live-fail-1",
        ticker_a="AAPL",
        ticker_b="MSFT",
        open_signals=[],
        max_open_pairs=8,
        block_shared_legs=True,
    )
    assert result.get("ok") is False
    assert result.get("reason") == "distributed_reservation_unavailable"
    assert not svc.has("live-fail-1")
