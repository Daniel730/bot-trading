import pytest
import asyncio
import time
import uuid
import logging
from src.services.execution_service_client import execution_client
from src.services.latency_service import latency_service
from src.generated.execution_pb2 import STATUS_SUCCESS

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_grpc_latency_audit():
    """
    Integration test to verify that gRPC RTT is being measured and pushed to Redis.
    Note: Requires a running Java Execution Engine on localhost:50051.
    """
    signal_id = str(uuid.uuid4())
    pair_id = "TEST_LATENCY"
    legs = [{
        "ticker": "AAPL",
        "side": "BUY",
        "quantity": 10.0,
        "target_price": 150.0
    }]
    
    # Execute trade
    logger.info(f"Sending test trade {signal_id}...")
    response = await execution_client.execute_trade(
        signal_id=signal_id,
        pair_id=pair_id,
        legs=legs
    )
    
    if not response:
        pytest.skip("Java Execution Engine not reachable at localhost:50051")
        
    # Wait a moment for the interceptor to finish pushing to Redis
    await asyncio.sleep(0.1)
    
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
