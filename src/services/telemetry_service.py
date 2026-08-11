"""Dashboard fan-out telemetry — fail-open, never blocks execution.

External tracing/errors belong to OpenTelemetry (#118) and Sentry (#119).
This module only queues updates for the operations-console WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.services.agent_log_service import agent_trace

logger = logging.getLogger(__name__)

_QUEUE_MAXSIZE = 10_000


class TelemetryService:
    """Internal dashboard telemetry bus (not a vendor APM client)."""

    def __init__(self, queue_maxsize: int = _QUEUE_MAXSIZE):
        # Explicitly no external HTTP sync endpoint — see sync_outcomes().
        self.external_sync_enabled = False
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        self._broadcast_task: Optional[asyncio.Task] = None
        self.dropped_updates = 0

    def start_broadcast_loop(self):
        """Start the background task that drains the queue to WebSockets."""
        if self._broadcast_task is None:
            self._broadcast_task = asyncio.create_task(self._broadcast_loop())
            logger.info("Telemetry: dashboard broadcast loop started.")

    async def _broadcast_loop(self):
        """Consume updates and fan out to dashboard WebSocket clients."""
        from src.services.dashboard_service import connection_manager

        while True:
            try:
                update = await self._queue.get()
                message = json.dumps(update)
                await connection_manager.broadcast(message)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Telemetry broadcast error: %s", e)
                await asyncio.sleep(1)

    def broadcast(self, type: str, data: Any):
        """Non-blocking fire-and-forget dashboard telemetry publish."""
        update = {
            "type": type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }

        try:
            self._queue.put_nowait(update)
        except asyncio.QueueFull:
            # Telemetry is best-effort; never block the execution hot path.
            self.dropped_updates += 1
            if self.dropped_updates == 1 or self.dropped_updates % 100 == 0:
                logger.warning(
                    "Telemetry queue full — dropped %s updates (fail-open)",
                    self.dropped_updates,
                )
        except Exception as e:
            logger.error("Error putting to telemetry queue: %s", e)

    @agent_trace("TelemetryService.sync_outcomes")
    async def sync_outcomes(self) -> dict:
        """External outcome sync is intentionally a no-op.

        Historical placeholder POSTed to a fake host. Real export is OTel/Sentry
        (issues #118/#119). Keep this method for call-site compatibility.
        """
        if not self.external_sync_enabled:
            logger.debug(
                "Telemetry sync_outcomes no-op (external sync disabled; use OTel/Sentry)."
            )
            return {
                "synced": False,
                "reason": "external_sync_disabled",
                "dropped_updates": self.dropped_updates,
            }
        logger.info("Telemetry: external sync enabled but no exporter configured.")
        return {
            "synced": False,
            "reason": "no_exporter_configured",
            "dropped_updates": self.dropped_updates,
        }


telemetry_service = TelemetryService()
