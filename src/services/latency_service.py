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

        # Decompose metrics
        rtts = []
        stale_times = []
        violations = 0
        
        for m in metrics:
            # RTT from Client perspective
            rtt = m.get('rtt_ns', 0) / 1_000_000
            rtts.append(rtt)
            
            # Alpha Stale Time = Server Received - Client Sent (T007)
            # Both are int64 nanoseconds
            sent = m.get('client_sent_ns', 0)
            received = m.get('server_received_ns', 0)
            if sent and received:
                stale_times.append((received - sent) / 1_000_000)
            
            # Violation check for FR-006
            if rtt > self.alarm_threshold_ms:
                violations += 1

        avg_rtt = np.mean(rtts)
        p95_rtt = np.percentile(rtts, 95)
        
        # FR-006: Trigger if RTT > 1ms for > 10% of samples
        violation_rate = violations / len(metrics)
        status = "HEALTHY"
        if violation_rate > 0.10:
            status = "DEGRADED"
            logger.error(f"LATENCY_ALARM: {violation_rate:.1%} of samples exceeded {self.alarm_threshold_ms}ms")
            # T009: Send alert via notification service
            # await notification_service.send_alert(f"gRPC Latency Alarm: {violation_rate:.1%} violations")

        report = {
            "sample_size": len(metrics),
            "avg_rtt_ms": float(avg_rtt),
            "p95_rtt_ms": float(p95_rtt),
            "avg_stale_time_ms": float(np.mean(stale_times)) if stale_times else 0,
            "violation_rate": float(violation_rate),
            "status": status
        }

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
