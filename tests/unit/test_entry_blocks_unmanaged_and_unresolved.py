"""Entry gates: unmanaged broker inventory + unresolved ledger must block new opens."""

from unittest.mock import AsyncMock

import pytest

from src.config import settings
from src.services.persistence_service import persistence_service


@pytest.mark.asyncio
async def test_entry_blocked_when_needs_manual_shares_pair_symbol(monitor, monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(
        persistence_service,
        "get_unresolved_exposure_tickers",
        AsyncMock(
            return_value=[
                {
                    "signal_id": "sig-manual",
                    "ticker": "DG",
                    "status": "NEEDS_MANUAL_RECONCILIATION",
                }
            ]
        ),
    )
    monkeypatch.setattr(persistence_service, "get_open_signals", AsyncMock(return_value=[]))

    blocked = await monitor._has_active_pair_or_pending_order("DG", "DLTR", notify=False)
    assert blocked is True


@pytest.mark.asyncio
async def test_entry_blocked_when_broker_has_unmanaged_leg_overlap(monitor, monkeypatch):
    """IGNORE_UNMANAGED continues scanning but must not average into foreign DG/DLTR."""
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(settings, "IGNORE_UNMANAGED_POSITIONS", True)
    monkeypatch.setattr(persistence_service, "get_open_signals", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        persistence_service,
        "get_unresolved_exposure_tickers",
        AsyncMock(return_value=[]),
    )
    monitor.brokerage.get_pending_orders = AsyncMock(return_value=[])
    monitor.brokerage.get_positions = AsyncMock(
        return_value=[
            {"ticker": "DG", "quantity": 12.0, "quantityAvailableForTrading": 12.0},
            {"ticker": "DLTR", "quantity": 8.0, "quantityAvailableForTrading": 8.0},
        ]
    )

    blocked = await monitor._has_active_pair_or_pending_order("DG", "DLTR", notify=False)
    assert blocked is True


@pytest.mark.asyncio
async def test_entry_allowed_when_broker_inventory_is_on_other_symbols(monitor, monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(persistence_service, "get_open_signals", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        persistence_service,
        "get_unresolved_exposure_tickers",
        AsyncMock(return_value=[]),
    )
    monitor.brokerage.get_pending_orders = AsyncMock(return_value=[])
    monitor.brokerage.get_positions = AsyncMock(
        return_value=[
            {"ticker": "A", "quantity": 5.0, "quantityAvailableForTrading": 5.0},
            {"ticker": "ULTA", "quantity": 3.0, "quantityAvailableForTrading": 3.0},
        ]
    )

    blocked = await monitor._has_active_pair_or_pending_order("KO", "PEP", notify=False)
    assert blocked is False


@pytest.mark.asyncio
async def test_entry_blocks_when_broker_positions_unreadable(monitor, monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRADING", False)
    monkeypatch.setattr(persistence_service, "get_open_signals", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        persistence_service,
        "get_unresolved_exposure_tickers",
        AsyncMock(return_value=[]),
    )
    monitor.brokerage.get_pending_orders = AsyncMock(return_value=[])
    monitor.brokerage.get_positions = AsyncMock(side_effect=RuntimeError("broker down"))

    blocked = await monitor._has_active_pair_or_pending_order("KO", "PEP", notify=False)
    assert blocked is True
