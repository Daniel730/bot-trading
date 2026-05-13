from types import SimpleNamespace
from unittest.mock import patch
import uuid

import pytest

from src.services.background_task_watchdog import background_task_watchdog
from src.services.persistence_service import ExitReason, PersistenceService


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.trade_metadata_updates = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def begin(self):
        return _FakeTransaction()

    async def execute(self, statement):
        if getattr(statement, "is_select", False):
            return _FakeResult(self.rows)

        if getattr(statement, "is_update", False):
            params = statement.compile().params
            metadata = params.get("metadata") or params.get("metadata_json")
            if metadata is not None:
                self.trade_metadata_updates.append(metadata)

        return SimpleNamespace()


@pytest.mark.asyncio
async def test_close_trade_preserves_entry_metadata(monkeypatch):
    signal_id = uuid.uuid4()
    rows = [
        SimpleNamespace(
            id=uuid.uuid4(),
            metadata_json={
                "broker_order_id": "leg-a-order",
                "client_order_id": "client-leg-a",
                "order_status": "LEG_A_FILLED",
            },
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            metadata_json={
                "broker_order_id": "leg-b-order",
                "client_order_id": "client-leg-b",
                "order_status": "LEG_B_FILLED",
            },
        ),
    ]
    fake_session = _FakeSession(rows)
    service = PersistenceService()
    monkeypatch.setattr(service, "AsyncSessionLocal", lambda: fake_session)

    def close_background_coro(coro, *, name):
        coro.close()

    with patch.object(background_task_watchdog, "create_task", side_effect=close_background_coro):
        await service.close_trade(
            signal_id,
            exit_prices={"AAPL": 151.0, "MSFT": 299.0},
            pnl=12.5,
            exit_reason=ExitReason.TAKE_PROFIT,
        )

    assert len(fake_session.trade_metadata_updates) == 2
    for existing_row, updated_metadata in zip(rows, fake_session.trade_metadata_updates):
        assert updated_metadata["broker_order_id"] == existing_row.metadata_json["broker_order_id"]
        assert updated_metadata["client_order_id"] == existing_row.metadata_json["client_order_id"]
        assert updated_metadata["order_status"] == existing_row.metadata_json["order_status"]
        assert updated_metadata["exit_prices"] == {"AAPL": 151.0, "MSFT": 299.0}
        assert updated_metadata["pnl"] == 12.5
        assert updated_metadata["exit_reason"] == ExitReason.TAKE_PROFIT.value
