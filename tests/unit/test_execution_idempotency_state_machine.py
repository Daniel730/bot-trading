import pytest
import grpc
from unittest.mock import AsyncMock

from src.generated import execution_pb2
from src.services.execution_service_client import ExecutionServiceClient


class _InMemRedis:
    def __init__(self):
        self.store = {}

    async def get_json(self, key):
        return self.store.get(key)

    async def set_json(self, key, value, ex=None):
        self.store[key] = value


def _patch_attempt_store_and_risk(monkeypatch, redis):
    monkeypatch.setattr("src.services.redis_service.redis_service", redis)
    monkeypatch.setattr(
        "src.services.risk_service.risk_service.get_execution_params",
        AsyncMock(return_value={"max_slippage_pct": 0.001, "risk_multiplier": 1.0}),
    )


@pytest.mark.asyncio
async def test_timeout_before_broker_call_retry_allowed(monkeypatch):
    client = ExecutionServiceClient()
    redis = _InMemRedis()
    _patch_attempt_store_and_risk(monkeypatch, redis)

    async def raise_before_dispatch(*args, **kwargs):
        raise RuntimeError("socket setup failed")

    monkeypatch.setattr(client, "get_stub", AsyncMock(side_effect=raise_before_dispatch))

    legs = [{"ticker": "AAPL", "side": "BUY", "quantity": 1, "target_price": 100}]
    resp1 = await client.execute_trade("sig-pre", "AAPL_MSFT", legs)
    assert resp1 is None
    assert redis.store["execution_attempt:sig-pre"]["state"] == "FAILED_BEFORE_SUBMIT"

    stub = AsyncMock()
    stub.ExecuteTrade.return_value = execution_pb2.ExecutionResponse(
        signal_id="sig-pre", status=execution_pb2.STATUS_SUCCESS, message="ok"
    )
    monkeypatch.setattr(client, "get_stub", AsyncMock(return_value=stub))
    resp2 = await client.execute_trade("sig-pre", "AAPL_MSFT", legs)
    assert resp2.status == execution_pb2.STATUS_SUCCESS
    assert stub.ExecuteTrade.call_count == 1


@pytest.mark.asyncio
async def test_timeout_after_dispatch_goes_unknown_and_retry_reconciles_no_duplicate(monkeypatch):
    client = ExecutionServiceClient()
    redis = _InMemRedis()
    _patch_attempt_store_and_risk(monkeypatch, redis)

    call_counter = {"n": 0}

    async def execute_side_effect(*args, **kwargs):
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            raise grpc.aio.AioRpcError(grpc.StatusCode.DEADLINE_EXCEEDED, None, None)  # type: ignore
        return execution_pb2.ExecutionResponse(signal_id="sig-unknown", status=execution_pb2.STATUS_SUCCESS)

    stub = AsyncMock()
    stub.ExecuteTrade.side_effect = execute_side_effect
    monkeypatch.setattr(client, "get_stub", AsyncMock(return_value=stub))
    monkeypatch.setattr(client, "get_trade_status", AsyncMock(return_value=execution_pb2.ExecutionResponse(signal_id="sig-unknown", status=execution_pb2.STATUS_SUCCESS)))

    legs = [{"ticker": "AAPL", "side": "BUY", "quantity": 1, "target_price": 100}]
    resp1 = await client.execute_trade("sig-unknown", "AAPL_MSFT", legs)
    assert resp1 is None
    assert redis.store["execution_attempt:sig-unknown"]["state"] == "UNKNOWN_REQUIRES_RECONCILIATION"

    resp2 = await client.execute_trade("sig-unknown", "AAPL_MSFT", legs)
    assert resp2.status == execution_pb2.STATUS_SUCCESS
    assert stub.ExecuteTrade.call_count == 1


@pytest.mark.asyncio
async def test_server_returns_none_marks_unknown_then_allows_retry_after_reconcile(monkeypatch):
    client = ExecutionServiceClient()
    redis = _InMemRedis()
    _patch_attempt_store_and_risk(monkeypatch, redis)

    stub = AsyncMock()
    stub.ExecuteTrade.side_effect = [None, execution_pb2.ExecutionResponse(signal_id="sig-none", status=execution_pb2.STATUS_SUCCESS)]
    monkeypatch.setattr(client, "get_stub", AsyncMock(return_value=stub))
    monkeypatch.setattr(client, "get_trade_status", AsyncMock(return_value=None))

    legs = [{"ticker": "AAPL", "side": "BUY", "quantity": 1, "target_price": 100}]
    r1 = await client.execute_trade("sig-none", "AAPL_MSFT", legs)
    assert r1 is None
    assert redis.store["execution_attempt:sig-none"]["state"] == "UNKNOWN_REQUIRES_RECONCILIATION"

    r2 = await client.execute_trade("sig-none", "AAPL_MSFT", legs)
    assert r2.status == execution_pb2.STATUS_SUCCESS
    assert stub.ExecuteTrade.call_count == 2


@pytest.mark.asyncio
async def test_unknown_reconcile_not_found_downgrades_and_retries(monkeypatch):
    client = ExecutionServiceClient()
    redis = _InMemRedis()
    redis.store["execution_attempt:sig-stale"] = {"state": "UNKNOWN_REQUIRES_RECONCILIATION"}
    _patch_attempt_store_and_risk(monkeypatch, redis)
    monkeypatch.setattr(client, "get_trade_status", AsyncMock(return_value=None))

    stub = AsyncMock()
    stub.ExecuteTrade.return_value = execution_pb2.ExecutionResponse(signal_id="sig-stale", status=execution_pb2.STATUS_SUCCESS)
    monkeypatch.setattr(client, "get_stub", AsyncMock(return_value=stub))

    legs = [{"ticker": "AAPL", "side": "BUY", "quantity": 1, "target_price": 100}]
    r = await client.execute_trade("sig-stale", "AAPL_MSFT", legs)
    assert r.status == execution_pb2.STATUS_SUCCESS
    assert stub.ExecuteTrade.call_count == 1


@pytest.mark.asyncio
async def test_adversarial_retry_does_not_duplicate_when_order_already_accepted(monkeypatch):
    client = ExecutionServiceClient()
    redis = _InMemRedis()
    redis.store["execution_attempt:sig-dup"] = {"state": "LOCKED_IN_FLIGHT"}
    _patch_attempt_store_and_risk(monkeypatch, redis)

    existing = execution_pb2.ExecutionResponse(signal_id="sig-dup", status=execution_pb2.STATUS_SUCCESS, message="already accepted")
    monkeypatch.setattr(client, "get_trade_status", AsyncMock(return_value=existing))

    stub = AsyncMock()
    monkeypatch.setattr(client, "get_stub", AsyncMock(return_value=stub))

    legs = [{"ticker": "AAPL", "side": "BUY", "quantity": 1, "target_price": 100}]
    r = await client.execute_trade("sig-dup", "AAPL_MSFT", legs)
    assert r.status == execution_pb2.STATUS_SUCCESS
    assert "already accepted" in r.message
    assert stub.ExecuteTrade.call_count == 0
