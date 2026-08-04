import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def test_redis_service_import_does_not_initialize_redis_client(monkeypatch):
    calls = []

    def fail_on_init(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Redis client must not be created during module import")

    monkeypatch.setattr("redis.asyncio.Redis", fail_on_init)
    module_name = "_redis_service_import_probe"
    module_path = Path(__file__).parents[2] / "src" / "services" / "redis_service.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

    assert calls == []
    assert module.redis_service is not None
    assert module.redis_service.get_json is not None
    assert calls == []


@pytest.mark.asyncio
async def test_save_kalman_state_applies_sliding_ttl(monkeypatch):
    from src.services import redis_service as rs_mod

    client = MagicMock()
    client.hset = AsyncMock()
    client.expire = AsyncMock()
    client.delete = AsyncMock(return_value=1)

    svc = object.__new__(rs_mod.RedisService)
    svc.client = client
    monkeypatch.setattr(rs_mod.settings, "KALMAN_STATE_TTL_SECONDS", 1209600)

    await svc.save_kalman_state(
        "BTC-USD_ETH-USD",
        x=[1.0, 0.5],
        P=[[1.0, 0.0], [0.0, 1.0]],
        z_score=1.25,
        innovation_variance=0.01,
        state_fingerprint="fp1",
    )

    client.hset.assert_awaited_once()
    key, kwargs = client.hset.await_args.args[0], client.hset.await_args.kwargs
    assert key == "kalman:BTC-USD_ETH-USD"
    assert "mapping" in kwargs
    assert kwargs["mapping"]["state_fingerprint"] == "fp1"
    client.expire.assert_awaited_once_with("kalman:BTC-USD_ETH-USD", 1209600)


@pytest.mark.asyncio
async def test_save_kalman_state_ttl_override(monkeypatch):
    from src.services import redis_service as rs_mod

    client = MagicMock()
    client.hset = AsyncMock()
    client.expire = AsyncMock()

    svc = object.__new__(rs_mod.RedisService)
    svc.client = client
    monkeypatch.setattr(rs_mod.settings, "KALMAN_STATE_TTL_SECONDS", 1209600)

    await svc.save_kalman_state(
        "KO_PEP",
        x=[0.0, 1.0],
        P=[[1.0]],
        z_score=0.0,
        ttl_seconds=3600,
    )
    client.expire.assert_awaited_once_with("kalman:KO_PEP", 3600)


@pytest.mark.asyncio
async def test_delete_kalman_state():
    from src.services import redis_service as rs_mod

    client = MagicMock()
    client.delete = AsyncMock(return_value=1)
    svc = object.__new__(rs_mod.RedisService)
    svc.client = client

    assert await svc.delete_kalman_state("A_B") == 1
    client.delete.assert_awaited_once_with("kalman:A_B")


def test_redis_key_namespaces_document_expected_ttls():
    from src.services.redis_service import REDIS_KEY_NAMESPACES

    assert "kalman" in REDIS_KEY_NAMESPACES
    assert "sec:integrity" in REDIS_KEY_NAMESPACES
    assert "sliding" in REDIS_KEY_NAMESPACES["kalman"]["ttl"].lower()
    assert "24h" in REDIS_KEY_NAMESPACES["sec:integrity"]["ttl"]


def test_redis_password_empty_becomes_none_for_client(monkeypatch):
    """Empty REDIS_PASSWORD must not send AUTH '' (breaks requirepass servers)."""
    from src.services import redis_service as rs_mod

    captured = {}

    class FakeRedis:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(rs_mod.redis, "Redis", FakeRedis)
    monkeypatch.setattr(rs_mod.settings, "REDIS_PASSWORD", "")
    rs_mod.RedisService._instance = None

    svc = rs_mod.RedisService()
    assert captured.get("password") is None
    rs_mod.RedisService._instance = None
