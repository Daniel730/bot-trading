import pytest
import asyncio
from contextlib import ExitStack
from unittest.mock import patch
from src.agents.orchestrator import Orchestrator
from src.models.persistence import PersistenceManager


def _route_system_state_to(db):
    """Redirect persistence_service.{get,set}_system_state at the in-memory
    SQLite db so the orchestrator's circuit-breaker counter is observable
    from the test, regardless of whether the real Postgres is reachable.

    The orchestrator's _set_system_state writes to Postgres first and only
    falls back to SQLite when Postgres raises. When CI provisions the
    Postgres schema, Postgres writes succeed and the legacy SQLite mock
    these tests inspect never sees the increments. Patching the singleton
    methods makes both reads and writes go to the same in-memory db.
    """
    async def fake_get(key, default=None):
        return db.get_system_state(key, default)

    async def fake_set(key, value):
        db.set_system_state(key, value)

    stack = ExitStack()
    stack.enter_context(
        patch('src.agents.orchestrator.persistence_service.get_system_state', new=fake_get)
    )
    stack.enter_context(
        patch('src.agents.orchestrator.persistence_service.set_system_state', new=fake_set)
    )
    return stack


@pytest.mark.asyncio
async def test_circuit_breaker_tripping():
    """
    T014: Verifies that Orchestrator trips to DEGRADED_MODE after 3 timeouts.
    """
    db = PersistenceManager(":memory:")
    db.set_system_state("operational_status", "NORMAL")
    db.set_system_state("consecutive_api_timeouts", "0")

    with patch('src.models.persistence.PersistenceManager', return_value=db), \
         _route_system_state_to(db), \
         patch('src.agents.orchestrator.macro_economic_agent.get_ticker_regime', return_value="BULLISH"):
        orchestrator = Orchestrator()

        input_data = {
            "signal_context": {"ticker_a": "AAPL", "ticker_b": "MSFT", "signal_id": "test_cb"}
        }

        with patch('src.agents.orchestrator.bull_agent.evaluate', side_effect=asyncio.TimeoutError()):
            await orchestrator.ainvoke(input_data)
            assert db.get_system_state("consecutive_api_timeouts") == "1"
            assert db.get_system_state("operational_status") == "NORMAL"

            await orchestrator.ainvoke(input_data)
            assert db.get_system_state("consecutive_api_timeouts") == "2"

            await orchestrator.ainvoke(input_data)
            assert db.get_system_state("consecutive_api_timeouts") == "3"
            assert db.get_system_state("operational_status") == "DEGRADED_MODE"

            result = await orchestrator.ainvoke(input_data)
            assert result["final_confidence"] == 0.0
            assert "DEGRADED_MODE" in result["final_verdict"]


@pytest.mark.asyncio
async def test_circuit_breaker_reset():
    """
    Verifies that successful execution resets the timeout count.
    """
    db = PersistenceManager(":memory:")
    db.set_system_state("consecutive_api_timeouts", "2")

    with patch('src.models.persistence.PersistenceManager', return_value=db), \
         _route_system_state_to(db), \
         patch('src.agents.orchestrator.macro_economic_agent.get_ticker_regime', return_value="BULLISH"):
        orchestrator = Orchestrator()

        with patch('src.agents.orchestrator.bull_agent.evaluate', return_value={"confidence": 0.5}):
            with patch('src.agents.orchestrator.bear_agent.evaluate', return_value={"confidence": 0.5}):
                with patch('src.agents.orchestrator.orchestrator.fundamental_analyst.analyze_ticker'):
                    await orchestrator.ainvoke({"signal_context": {"ticker_a": "X", "ticker_b": "Y"}})
                    assert db.get_system_state("consecutive_api_timeouts") == "0"


if __name__ == "__main__":
    asyncio.run(test_circuit_breaker_tripping())
    asyncio.run(test_circuit_breaker_reset())
