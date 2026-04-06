import logging
import numpy as np
from typing import Dict, List, Optional
from src.services.redis_service import redis_service
from src.services.notification_service import notification_service
from src.config import settings

logger = logging.getLogger(__name__)

class LatencyService:
    def __init__(self, alarm_threshold_ms: float = 1.0):
        self.alarm_threshold_ms = alarm_threshold_ms

    async def get_performance_report(self, count: int = 100) -> Dict:
        """
        Aggregates recent latency metrics and returns a report.
        """
        metrics = await redis_service.get_recent_latency(count)
        if not metrics:
            return {"status": "no_data"}

        rtts = [m['rtt_ns'] / 1_000_000 for m in metrics]
        
        avg_rtt = np.mean(rtts)
        p95_rtt = np.percentile(rtts, 95)
        p99_rtt = np.percentile(rtts, 99)
        max_rtt = np.max(rtts)

        report = {
            "sample_size": len(metrics),
            "avg_rtt_ms": float(avg_rtt),
            "p95_rtt_ms": float(p95_rtt),
            "p99_rtt_ms": float(p99_rtt),
            "max_rtt_ms": float(max_rtt),
            "status": "HEALTHY" if avg_rtt < self.alarm_threshold_ms else "DEGRADED"
        }

        # Check for alarm trigger (T016)
        if avg_rtt > self.alarm_threshold_ms:
            logger.warning(f"LATENCY_ALARM: Average RTT {avg_rtt:.3f}ms exceeds threshold {self.alarm_threshold_ms}ms")
            # Notification logic can be triggered here or in Phase 6
            # await notification_service.send_alert(f"gRPC Latency Alarm: Avg RTT {avg_rtt:.2f}ms")

        return report

    async def log_latency(self, signal_id: str, rtt_ns: int, server_received_ns: int = 0, server_processed_ns: int = 0):
        """
        Directly log a latency event (can be used by non-interceptor flows).
        """
        metrics = {
            "signal_id": signal_id,
            "rtt_ns": rtt_ns,
            "server_received_ns": server_received_ns,
            "server_processed_ns": server_processed_ns,
            "client_sent_ns": 0, # Placeholder if not coming from interceptor
            "client_received_ns": 0
        }
        await redis_service.push_latency_metrics(metrics)

latency_service = LatencyService(alarm_threshold_ms=settings.LATENCY_ALARM_THRESHOLD_MS)
