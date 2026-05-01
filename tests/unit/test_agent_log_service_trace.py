"""
Unit tests for the agent_trace decorator in agent_log_service.py.

This PR changed the coroutine detection from asyncio.iscoroutinefunction to
inspect.iscoroutinefunction. The latter correctly handles functions wrapped
with functools.wraps or other decorators that asyncio.iscoroutinefunction
may fail to detect as coroutines.
"""
import asyncio
import functools

import pytest

from src.services.agent_log_service import agent_logger, agent_trace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_breadcrumbs():
    """Clear any leftover breadcrumbs between tests."""
    from src.services.agent_log_service import _BREADCRUMBS
    _BREADCRUMBS.set([])


# ---------------------------------------------------------------------------
# Async function detection
# ---------------------------------------------------------------------------

class TestAgentTraceAsyncDetection:
    def setup_method(self):
        _reset_breadcrumbs()

    def teardown_method(self):
        _reset_breadcrumbs()

    @pytest.mark.asyncio
    async def test_async_function_returns_awaitable(self):
        """Decorated async functions must remain awaitable."""

        @agent_trace("step_async")
        async def my_async_func():
            return "async_result"

        result = await my_async_func()
        assert result == "async_result"

    def test_sync_function_returns_directly(self):
        """Decorated sync functions must remain callable (not awaitable)."""

        @agent_trace("step_sync")
        def my_sync_func():
            return "sync_result"

        result = my_sync_func()
        assert result == "sync_result"
        assert not asyncio.iscoroutine(result)

    @pytest.mark.asyncio
    async def test_wrapped_async_function_still_detected_as_async(self):
        """
        inspect.iscoroutinefunction correctly detects async even when
        functools.wraps is applied — the key fix compared to asyncio.iscoroutinefunction.
        """

        async def inner():
            return "wrapped_async"

        @functools.wraps(inner)
        async def outer():
            return await inner()

        @agent_trace("wrapped_step")
        @functools.wraps(inner)
        async def double_wrapped():
            return await inner()

        result = await double_wrapped()
        assert result == "wrapped_async"


# ---------------------------------------------------------------------------
# Breadcrumb push/pop behaviour
# ---------------------------------------------------------------------------

class TestAgentTraceBreadcrumbs:
    def setup_method(self):
        _reset_breadcrumbs()

    def teardown_method(self):
        _reset_breadcrumbs()

    @pytest.mark.asyncio
    async def test_async_wrapper_pushes_and_pops_breadcrumb(self):
        observed = []

        @agent_trace("my_step")
        async def capturing_func():
            observed.append(agent_logger.get_path())

        await capturing_func()

        assert observed == ["my_step"]
        # After the call the breadcrumb must have been popped
        assert agent_logger.get_path() == ""

    def test_sync_wrapper_pushes_and_pops_breadcrumb(self):
        observed = []

        @agent_trace("sync_step")
        def capturing_func():
            observed.append(agent_logger.get_path())

        capturing_func()

        assert observed == ["sync_step"]
        assert agent_logger.get_path() == ""

    @pytest.mark.asyncio
    async def test_nested_async_traces_build_path(self):
        observed = []

        @agent_trace("outer")
        async def outer():
            @agent_trace("inner")
            async def inner():
                observed.append(agent_logger.get_path())

            await inner()
            observed.append(agent_logger.get_path())

        await outer()

        assert observed[0] == "outer -> inner"
        assert observed[1] == "outer"
        assert agent_logger.get_path() == ""

    def test_breadcrumb_popped_even_on_sync_exception(self):
        @agent_trace("failing_step")
        def failing_func():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            failing_func()

        assert agent_logger.get_path() == ""

    @pytest.mark.asyncio
    async def test_breadcrumb_popped_even_on_async_exception(self):
        @agent_trace("async_failing_step")
        async def failing_func():
            raise RuntimeError("async boom")

        with pytest.raises(RuntimeError, match="async boom"):
            await failing_func()

        assert agent_logger.get_path() == ""


# ---------------------------------------------------------------------------
# Exception path annotation
# ---------------------------------------------------------------------------

class TestAgentTraceExceptionPath:
    def setup_method(self):
        _reset_breadcrumbs()

    def teardown_method(self):
        _reset_breadcrumbs()

    def test_sync_exception_receives_agent_path_attribute(self):
        @agent_trace("annotated_step")
        def broken():
            raise ValueError("broken")

        try:
            broken()
        except ValueError as exc:
            assert hasattr(exc, "__agent_path__")
            assert "annotated_step" in exc.__agent_path__

    @pytest.mark.asyncio
    async def test_async_exception_receives_agent_path_attribute(self):
        @agent_trace("async_annotated")
        async def async_broken():
            raise RuntimeError("async broken")

        try:
            await async_broken()
        except RuntimeError as exc:
            assert hasattr(exc, "__agent_path__")
            assert "async_annotated" in exc.__agent_path__

    def test_existing_path_attribute_is_not_overwritten(self):
        """If an exception already has __agent_path__ set, the decorator must not replace it."""

        @agent_trace("outer_trace")
        def outer():
            @agent_trace("inner_trace")
            def inner():
                err = ValueError("nested")
                err.__agent_path__ = "already_set"
                raise err

            inner()

        try:
            outer()
        except ValueError as exc:
            # The inner decorator sets the path first; outer should not overwrite it
            assert exc.__agent_path__ == "already_set"


# ---------------------------------------------------------------------------
# functools.wraps preservation
# ---------------------------------------------------------------------------

class TestAgentTraceFunctoolsWraps:
    def test_sync_wrapper_preserves_function_metadata(self):
        @agent_trace("meta_step")
        def documented_func():
            """My docstring."""
            pass

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "My docstring."

    @pytest.mark.asyncio
    async def test_async_wrapper_preserves_function_metadata(self):
        @agent_trace("async_meta_step")
        async def async_documented_func():
            """Async docstring."""
            pass

        assert async_documented_func.__name__ == "async_documented_func"
        assert async_documented_func.__doc__ == "Async docstring."