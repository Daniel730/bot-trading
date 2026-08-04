"""Tests for unmanaged broker position acknowledgement (no OPEN ledger import)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.services.unmanaged_positions_service import (
    acknowledge_symbols,
    classify_broker_positions,
    filter_unacked_symbols,
    load_acknowledgements,
)


def test_classify_splits_managed_unmanaged_and_acknowledged():
    broker = [
        {"ticker": "BTC-USD", "quantity": 0.1, "marketValue": 11000},
        {"ticker": "AAPL", "quantity": 5, "marketValue": 1000},
        {"ticker": "ETH-USD", "quantity": 1.0, "marketValue": 3000},
    ]
    open_signals = [
        {
            "signal_id": "sig-1",
            "legs": [
                {"ticker": "AAPL", "quantity": 5, "side": "BUY"},
                {"ticker": "MSFT", "quantity": 2, "side": "SELL"},
            ],
        }
    ]
    acks = {
        "symbols": {
            "ETH-USD": {"symbol": "ETH-USD", "note": "reviewed"},
        }
    }
    result = classify_broker_positions(broker, open_signals, acks)
    assert [r["symbol"] for r in result["managed"]] == ["AAPL"]
    assert result["unmanaged_symbols"] == ["BTC-USD"]
    assert result["acknowledged_symbols"] == ["ETH-USD"]


def test_filter_unacked_symbols_drops_acknowledged():
    remaining = filter_unacked_symbols(
        ["BTC-USD", "ETH-USD", "SOL-USD"],
        {"symbols": {"ETH-USD": {}, "SOL-USD": {}}},
    )
    assert remaining == ["BTC-USD"]


@pytest.mark.asyncio
async def test_acknowledge_symbols_persists_provenance_without_open_signals():
    stored = {}

    async def _get(key, default=None):
        return stored.get(key, default)

    async def _set(key, value):
        stored[key] = value

    with patch(
        "src.services.unmanaged_positions_service.persistence_service.get_system_state",
        new=AsyncMock(side_effect=_get),
    ), patch(
        "src.services.unmanaged_positions_service.persistence_service.set_system_state",
        new=AsyncMock(side_effect=_set),
    ):
        payload = await acknowledge_symbols(
            symbols=["BTC-USD"],
            positions=[{"ticker": "BTC-USD", "quantity": 0.12, "marketValue": 11000}],
            actor="test",
            note="paper_ack",
        )
        loaded = await load_acknowledgements()

    assert "BTC-USD" in payload["symbols"]
    assert payload["symbols"]["BTC-USD"]["provenance"] == "broker_foreign_holding"
    assert loaded["symbols"]["BTC-USD"]["actor"] == "test"
    assert json.loads(stored["unmanaged_positions_acknowledged"])["symbols"]["BTC-USD"]["note"] == "paper_ack"
