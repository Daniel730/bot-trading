import pytest
from src.services.latency_service import LatencyService
import numpy as np

@pytest.fixture
def latency_service():
    return LatencyService(alarm_threshold_ms=1.0)

@pytest.mark.asyncio
async def test_alpha_stale_time_calculation(latency_service, mocker):
    # Mock redis to return specific metrics
    # sent=0, received=500,000ns (0.5ms)
    mock_metrics = [
        {
            "signal_id": "test_1",
            "client_sent_ns": 1000000000,
            "server_received_ns": 1000500000, # 0.5ms stale
            "rtt_ns": 800000 # 0.8ms RTT
        }
    ]
    mocker.patch("src.services.redis_service.redis_service.get_recent_latency", return_value=mock_metrics)
    
    report = await latency_service.get_performance_report()
    
    assert report["avg_stale_time_ms"] == 0.5
    assert report["avg_rtt_ms"] == 0.8
    assert report["status"] == "HEALTHY"

@pytest.mark.asyncio
async def test_latency_alarm_trigger(latency_service, mocker):
    # Mock redis to return 20% violations (2 out of 10)
    # FR-006: Trigger if > 10%
    mock_metrics = []
    for i in range(8):
        mock_metrics.append({"rtt_ns": 800000}) # 0.8ms (Healthy)
    for i in range(2):
        mock_metrics.append({"rtt_ns": 1200000}) # 1.2ms (Violation)
        
    mocker.patch("src.services.redis_service.redis_service.get_recent_latency", return_value=mock_metrics)
    
    report = await latency_service.get_performance_report()
    
    assert report["violation_rate"] == 0.2
    assert report["status"] == "DEGRADED"

@pytest.mark.asyncio
async def test_empty_metrics_handling(latency_service, mocker):
    mocker.patch("src.services.redis_service.redis_service.get_recent_latency", return_value=[])
    report = await latency_service.get_performance_report()
    assert report["status"] == "no_data"
