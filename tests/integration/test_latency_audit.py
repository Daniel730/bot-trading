import pytest
import asyncio
import time
import uuid
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.execution_service_client import execution_client
from src.services.latency_service import latency_service
from src.generated import execution_pb2
from src.generated.execution_pb2 import STATUS_SUCCESS

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_grpc_latency_audit():
    """
    Integration test to verify that gRPC RTT reporting is read from Redis latency samples.
    """
    signal_id = str(uuid.uuid4())
    pair_id = "TEST_LATENCY"
    legs = [{
        "ticker": "AAPL",
        "side": "BUY",
        "quantity": 10.0,
        "target_price": 150.0
    }]
    
    mock_stub = MagicMock()
    mock_stub.ExecuteTrade = AsyncMock(return_value=execution_pb2.ExecutionResponse(
        signal_id=signal_id,
        status=STATUS_SUCCESS,
        message="Simulated execution accepted",
    ))
    mock_latency_metrics = [{
        "signal_id": signal_id,
        "client_sent_ns": time.perf_counter_ns(),
        "client_received_ns": time.perf_counter_ns() + 250_000,
        "server_received_ns": time.perf_counter_ns() + 50_000,
        "server_processed_ns": time.perf_counter_ns() + 150_000,
        "rtt_ns": 250_000,
        "status": "OK",
    }]

    with patch('src.services.redis_service.redis_service.get_json', new=AsyncMock(return_value=None)) as mock_get_json, \
         patch('src.services.redis_service.redis_service.set_json', new=AsyncMock()) as mock_set_json, \
         patch('src.services.redis_service.redis_service.get_recent_latency', new=AsyncMock(return_value=mock_latency_metrics)), \
         patch('src.services.risk_service.risk_service.get_execution_params', new=AsyncMock(return_value={
             "max_slippage_pct": 0.001,
             "risk_multiplier": 1.0,
         })), \
         patch.object(execution_client, 'get_stub', new=AsyncMock(return_value=mock_stub)):
        # Execute trade
        logger.info(f"Sending test trade {signal_id}...")
        response = await execution_client.execute_trade(
            signal_id=signal_id,
            pair_id=pair_id,
            legs=legs
        )
        mock_get_json.assert_awaited_once_with(f"execution_attempt:{signal_id}")
        assert mock_set_json.await_count == 2
    
        assert response.status == STATUS_SUCCESS
        
        # Verify report
        report = await latency_service.get_performance_report(count=10)
    logger.info(f"Latency Report: {report}")
    
    assert report["sample_size"] > 0
    assert "avg_rtt_ms" in report
    assert report["avg_rtt_ms"] > 0
    
    # Sub-millisecond check (warning level)
    if report["avg_rtt_ms"] > 1.0:
        logger.warning(f"Latency Audit: Avg RTT is {report['avg_rtt_ms']:.3f}ms (> 1ms target)")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_grpc_latency_audit())
