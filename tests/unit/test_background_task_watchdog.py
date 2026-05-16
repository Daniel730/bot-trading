import asyncio

import pytest

from src.services.background_task_watchdog import background_task_watchdog
from src.services.dashboard_service import dashboard_service


@pytest.mark.asyncio
async def test_background_task_failure_surfaces_in_health():
    background_task_watchdog.reset()

    try:
        async def failing_task():
            await asyncio.sleep(0)
            raise RuntimeError("watchdog boom")

        task = background_task_watchdog.create_task(
            failing_task(),
            name="unit-test-failing-task",
        )

        await asyncio.gather(task, return_exceptions=True)

        snapshot = dashboard_service.health_snapshot()
        background_tasks = snapshot["background_tasks"]

        assert snapshot["status"] == "degraded"
        assert background_tasks["failed_count"] == 1
        assert background_tasks["last_failure"]["name"] == "unit-test-failing-task"
        assert background_tasks["last_failure"]["exception_type"] == "RuntimeError"
        assert "watchdog boom" in background_tasks["last_failure"]["message"]
    finally:
        background_task_watchdog.reset()
