import unittest

import pytest

from tests.benchmark import test_value_traps


@pytest.mark.asyncio
async def test_value_trap_benchmark_requires_explicit_live_opt_in(monkeypatch):
    monkeypatch.delenv("RUN_LIVE_BENCHMARKS", raising=False)
    monkeypatch.setattr(test_value_traps.settings, "GEMINI_API_KEY", "real-key")
    monkeypatch.setattr(test_value_traps.fundamental_analyst, "model", object())

    case = test_value_traps.ValueTrapBenchmark(methodName="test_historical_value_traps")

    with pytest.raises(unittest.SkipTest, match="RUN_LIVE_BENCHMARKS=1"):
        await case.asyncSetUp()
