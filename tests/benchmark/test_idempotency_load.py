import pytest
import asyncio
from src.services.execution_service_client import ExecutionServiceClient
from src.generated import execution_pb2
import uuid

@pytest.mark.asyncio
async def test_idempotency_concurrency_load(mocker):
    # Setup client
    client = ExecutionServiceClient()
    
    # Mock Redis NX to return True only once for a specific key
    processed_keys = set()
    async def mock_set_nx(key, value, expire=60):
        if key in processed_keys:
            return False
        processed_keys.add(key)
        return True
    
    mocker.patch("src.services.redis_service.redis_service.set_nx", side_effect=mock_set_nx)
    
    # Mock gRPC call to always succeed
    mock_response = execution_pb2.ExecutionResponse(
        signal_id="test_signal",
        status=execution_pb2.STATUS_SUCCESS
    )
    
    # We mock get_stub to return a mock stub
    mock_stub = mocker.AsyncMock()
    mock_stub.ExecuteTrade.return_value = mock_response
    mocker.patch.object(client, "get_stub", return_value=mock_stub)

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
    success_count = 0
    duplicate_count = 0
    for res in results:
        if res.status == execution_pb2.STATUS_SUCCESS:
            success_count += 1
        elif "Duplicate Request" in res.message:
            duplicate_count += 1

    # Only 1 should succeed, 99 should be rejected as duplicates
    assert success_count == 1
    assert duplicate_count == 99
    
    # Verify gRPC was only called ONCE
    assert mock_stub.ExecuteTrade.call_count == 1
