import requests
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from src.services.persistence_service import persistence_service
from src.services.agent_log_service import agent_trace
import logging

logger = logging.getLogger(__name__)

class TelemetryService:
    def __init__(self):
        self.endpoint = "https://api.arbitrage-elite.com/telemetry" # Placeholder
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._broadcast_task: Optional[asyncio.Task] = None

    def start_broadcast_loop(self):
        """Starts the background task that drains the queue and broadcasts to WebSockets."""
        if self._broadcast_task is None:
            self._broadcast_task = asyncio.create_task(self._broadcast_loop())
            logger.info("Telemetry: Broadcast loop started.")

    async def _broadcast_loop(self):
        """Consumes updates from the queue and sends to Dashboard WebSocket clients."""
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
                logger.error(f"Telemetry broadcast error: {e}")
                await asyncio.sleep(1)

    def broadcast(self, type: str, data: Any):
        """
        Non-blocking 'fire-and-forget' telemetry broadcast.
        Pushes a message to the internal queue for background processing.
        """
        update = {
            "type": type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        
        try:
            # Atomic non-blocking push
            self._queue.put_nowait(update)
        except asyncio.QueueFull:
            logger.warning("Telemetry: Queue full. Dropping oldest record.")
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(update)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error putting to telemetry queue: {e}")

    @agent_trace("TelemetryService.sync_outcomes")
    async def sync_outcomes(self):
        """
        Batches unsynced TelemetryRecords and POSTs them to a central endpoint.
        Uses PostgreSQL SystemState for tracking or a dedicated table.
        For MVP, we'll just log that syncing is occurring.
        """
        # Placeholder for real telemetry syncing logic using persistence_service
        logger.info("Telemetry: Syncing records to central server (Stub).")

telemetry_service = TelemetryService()
