import importlib.util
import sys
from pathlib import Path


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
