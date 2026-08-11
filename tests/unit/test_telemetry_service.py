"""TelemetryService fail-open / queue overflow contracts."""

from __future__ import annotations

import pytest

from src.services.telemetry_service import TelemetryService


@pytest.mark.asyncio
async def test_broadcast_drops_when_queue_full_without_raising():
    service = TelemetryService(queue_maxsize=1)
    service.broadcast("tick", {"n": 1})
    service.broadcast("tick", {"n": 2})  # overflow
    service.broadcast("tick", {"n": 3})  # overflow again
    assert service.dropped_updates == 2
    assert service._queue.qsize() == 1


@pytest.mark.asyncio
async def test_sync_outcomes_is_explicit_noop():
    service = TelemetryService()
    result = await service.sync_outcomes()
    assert result["synced"] is False
    assert result["reason"] == "external_sync_disabled"
    assert "api.arbitrage-elite.com" not in repr(service.__dict__)


def test_no_placeholder_http_endpoint_attribute():
    service = TelemetryService()
    assert not hasattr(service, "endpoint") or not service.__dict__.get("endpoint")
    assert service.external_sync_enabled is False
