from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_pytest_default_excludes_live_benchmark_and_real_redis_markers():
    config = (ROOT / "pytest.ini").read_text(encoding="utf-8")

    assert "not live and not benchmark and not redis_real" in config
    assert "live:" in config
    assert "benchmark:" in config
    assert "redis_real:" in config


@pytest.mark.parametrize(
    ("path", "marker"),
    [
        ("tests/benchmark/test_idempotency_load.py", "benchmark"),
        ("tests/benchmark/test_value_traps.py", "benchmark"),
        ("tests/integration/test_cik_ground_truth.py", "live"),
    ],
)
def test_real_environment_tests_have_explicit_markers(path, marker):
    contents = (ROOT / path).read_text(encoding="utf-8")

    assert f"pytestmark = pytest.mark.{marker}" in contents
