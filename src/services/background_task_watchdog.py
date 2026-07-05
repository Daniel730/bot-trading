import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Coroutine


logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BackgroundTaskWatchdog:
    def __init__(self, max_events: int = 50):
        self._max_events = max_events
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._tasks: dict[int, dict[str, Any]] = {}
        self._next_task_id = 0

    def create_task(self, coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task:
        self._next_task_id += 1
        task_id = self._next_task_id
        started_at = _utcnow_iso()
        task = asyncio.create_task(coro, name=name)
        self._tasks[task_id] = {
            "id": task_id,
            "name": name,
            "started_at": started_at,
            "task": task,
        }
        task.add_done_callback(
            lambda done_task, done_task_id=task_id: self._record_completion(done_task_id, done_task)
        )
        return task

    def _record_completion(self, task_id: int, task: asyncio.Task) -> None:
        tracked = self._tasks.pop(task_id, None)
        name = tracked["name"] if tracked else task.get_name()
        started_at = tracked.get("started_at") if tracked else None
        event: dict[str, Any] = {
            "id": task_id,
            "name": name,
            "started_at": started_at,
            "finished_at": _utcnow_iso(),
        }

        if task.cancelled():
            event["status"] = "cancelled"
        else:
            exc = task.exception()
            if exc is None:
                event["status"] = "completed"
            else:
                event.update(
                    {
                        "status": "failed",
                        "exception_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
                logger.error(
                    "Background task failed: %s",
                    name,
                    exc_info=(type(exc), exc, exc.__traceback__),
                )

        self._events.append(event)

    def snapshot(self) -> dict[str, Any]:
        active = [
            {
                "id": task_id,
                "name": tracked["name"],
                "started_at": tracked["started_at"],
            }
            for task_id, tracked in sorted(self._tasks.items())
        ]
        events = list(self._events)
        failures = [event for event in events if event.get("status") == "failed"]
        return {
            "active_count": len(active),
            "active": active,
            "failed_count": len(failures),
            "last_failure": failures[-1] if failures else None,
            "recent_events": events,
        }

    def reset(self) -> None:
        self._events.clear()
        self._tasks.clear()
        self._next_task_id = 0


background_task_watchdog = BackgroundTaskWatchdog()
