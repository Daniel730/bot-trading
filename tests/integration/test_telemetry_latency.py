import pytest
import asyncio
import time
import uuid
from unittest.mock import MagicMock, patch
from src.services.telemetry_service import telemetry_service
from src.services.execution_service_client import execution_client
from src.services.dashboard_service import connection_manager

@pytest.mark.asyncio
async def test_telemetry_fire_and_forget_latency():
    """
    US3: Verify that telemetry broadcast has near-zero overhead on the calling thread.
    """
    # 1. Warm up
    telemetry_service.broadcast("status", {"details": "Warm up"})
    
    # 2. Measure latency of broadcast call
    start_time = time.perf_counter_ns()
    
    # Simulate a burst of 100 broadcasts
    for i in range(100):
        telemetry_service.broadcast("thought", {
            "agent_name": "TEST",
            "thought": f"Message {i}"
        })
        
    end_time = time.perf_counter_ns()
    
    total_latency_ms = (end_time - start_time) / 1_000_000
    avg_latency_per_call_ms = total_latency_ms / 100
    
    print(f"\nTelemetry Broadcast Latency: {avg_latency_per_call_ms:.6f} ms per call")
    
    # The call should be extremely fast as it just pushes to a local queue
    assert avg_latency_per_call_ms < 0.5 # Sub-millisecond

@pytest.mark.asyncio
async def test_broadcast_non_blocking_with_failed_client():
    """
    US3: Verify that a slow or failing WebSocket broadcast does not block the producer.
    """
    # 1. Start the broadcast loop
    telemetry_service.start_broadcast_loop()
    
    # 2. Mock a connection that blocks or fails
    mock_ws = MagicMock()
    # Mock accept as an async method
    async def mock_accept(): pass
    mock_ws.accept = mock_accept
    
    # Mock send_text to be a slow coroutine
    async def slow_send(msg):
        await asyncio.sleep(0.5)
        raise Exception("Simulated connection failure")
        
    mock_ws.send_text = slow_send
    
    await connection_manager.connect(mock_ws)
    
    # 3. Measure producer latency
    start_time = time.perf_counter_ns()
    telemetry_service.broadcast("risk", {"risk_multiplier": 1.0})
    end_time = time.perf_counter_ns()
    
    producer_latency_ms = (end_time - start_time) / 1_000_000
    print(f"Producer Latency with failing client: {producer_latency_ms:.6f} ms")
    
    # Producer should NOT wait for the 0.5s sleep in the consumer loop
    assert producer_latency_ms < 1.0 
    
    # Cleanup
    connection_manager.disconnect(mock_ws)

@pytest.mark.asyncio
async def test_full_execution_hotpath_latency():
    """
    US3: Verify that the end-to-end execution path (including risk calculation and telemetry)
    remains within the latency budget.
    """
    from src.services.risk_service import risk_service
    from src.services.redis_service import redis_service
    
    signal_id = str(uuid.uuid4())
    legs = [{"ticker": "KO", "side": "BUY", "quantity": 100, "target_price": 60.0}]
    
    # Mock everything except the telemetry call
    with patch.object(redis_service, 'set_nx', return_value=True), \
         patch.object(execution_client, 'get_stub') as mock_stub_factory, \
         patch.object(redis_service, 'get_json', return_value={"bids": [[60, 100]], "asks": [[60.1, 100]]}):
        
        mock_stub = MagicMock()
        mock_execute = MagicMock()
        future = asyncio.Future()
        future.set_result(MagicMock(status=1))
        mock_execute.return_value = future
        mock_stub.ExecuteTrade = mock_execute
        mock_stub_factory.return_value = mock_stub
        
        # Start broadcast loop to ensure background task is running
        telemetry_service.start_broadcast_loop()

        start_time = time.perf_counter_ns()
        
        # This call now includes RiskService.get_execution_params -> telemetry_service.broadcast
        await execution_client.execute_trade(signal_id, "KO_PEP", legs)
        
        end_time = time.perf_counter_ns()
        
        execution_latency_ms = (end_time - start_time) / 1_000_000
        print(f"Full Execution Hotpath Latency: {execution_latency_ms:.6f} ms")
        
        # We allow up to 100ms for CI environment jitter, but logically it should be very low
        assert execution_latency_ms < 100.0 
