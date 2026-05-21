import pytest
import asyncio
from unittest.mock import AsyncMock
from src.services.execution_service_client import ExecutionServiceClient
from src.generated import execution_pb2
import uuid


class _ConcurrentAttemptStore:
    def __init__(self):
        self.store = {}
        self.locks = set()
        self.client = _ConcurrentAttemptStoreClient(self)
        self.load_count = 0

    async def get_json(self, key):
        self.load_count += 1
        if self.load_count == 1:
            return None
        return self.store.get(key, {"state": "LOCKED_IN_FLIGHT"})

    async def set_json(self, key, value, ex=None):
        self.store[key] = value

    async def set_json_nx(self, key, value, ex=None):
        if key in self.locks:
            return False
        self.locks.add(key)
        return True

    async def delete(self, key):
        self.locks.discard(key)
        return 1


class _ConcurrentAttemptStoreClient:
    def __init__(self, owner):
        self.owner = owner

    async def delete(self, key):
        self.owner.locks.discard(key)
        return 1


@pytest.mark.asyncio
async def test_idempotency_concurrency_load(monkeypatch):
    # Setup client
    client = ExecutionServiceClient()
    redis = _ConcurrentAttemptStore()
    monkeypatch.setattr("src.services.redis_service.redis_service", redis)
    monkeypatch.setattr(
        "src.services.risk_service.risk_service.get_execution_params",
        AsyncMock(return_value={"max_slippage_pct": 0.001, "risk_multiplier": 1.0}),
    )
    
    # Mock gRPC call to always succeed
    mock_response = execution_pb2.ExecutionResponse(
        signal_id="test_signal",
        status=execution_pb2.STATUS_SUCCESS,
        message="accepted",
    )
    
    # We mock get_stub to return a mock stub
    mock_stub = AsyncMock()
    mock_stub.ExecuteTrade.return_value = mock_response
    monkeypatch.setattr(client, "get_stub", AsyncMock(return_value=mock_stub))
    mock_status = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(client, "get_trade_status", mock_status)

    # Simulate 100 concurrent requests for the SAME signal_id
    signal_id = str(uuid.uuid4())
    tasks = []
    for _ in range(100):
        tasks.append(client.execute_trade(
            signal_id=signal_id,
            pair_id="AAPL_MSFT",
            legs=[{"ticker": "AAPL", "side": "BUY", "quantity": 10, "target_price": 150.0}]
        ))

    results = await asyncio.gather(*tasks)

    # Verify Results
    success_count = sum(1 for res in results if res.status == execution_pb2.STATUS_SUCCESS)

    # Only 1 should dispatch; the rest reconcile the in-flight/accepted attempt.
    assert success_count == 100
    
    # Verify gRPC was only called ONCE
    assert mock_stub.ExecuteTrade.call_count == 1
    assert mock_status.await_count == 99
