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
        """
        Reset global breadcrumb state before each test method by clearing the agent logger's breadcrumb list.
        """
        _reset_breadcrumbs()

    def teardown_method(self):
        """
        Reset shared breadcrumb state after each test completes.
        """
        _reset_breadcrumbs()

    @pytest.mark.asyncio
    async def test_async_function_returns_awaitable(self):
        """Decorated async functions must remain awaitable."""

        @agent_trace("step_async")
        async def my_async_func():
            """
            Provide a constant test result string used by tests.
            
            Returns:
                str: The constant string 'async_result'.
            """
            return "async_result"

        result = await my_async_func()
        assert result == "async_result"

    def test_sync_function_returns_directly(self):
        """Decorated sync functions must remain callable (not awaitable)."""

        @agent_trace("step_sync")
        def my_sync_func():
            """
            Provide a synchronous test function that returns a fixed result string.
            
            Returns:
                str: The fixed value "sync_result".
            """
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
            """
            Return a sentinel string used by tests for wrapped async functions.
            
            Returns:
                str: The sentinel string "wrapped_async".
            """
            return "wrapped_async"

        @functools.wraps(inner)
        async def outer():
            """
            Call the inner coroutine and return its result.
            
            Returns:
                The value returned by `inner`.
            """
            return await inner()

        @agent_trace("wrapped_step")
        @functools.wraps(inner)
        async def double_wrapped():
            """
            Invoke the wrapped inner coroutine and return its result.
            
            Returns:
                The value returned by the `inner` coroutine.
            """
            return await inner()

        result = await double_wrapped()
        assert result == "wrapped_async"


# ---------------------------------------------------------------------------
# Breadcrumb push/pop behaviour
# ---------------------------------------------------------------------------

class TestAgentTraceBreadcrumbs:
    def setup_method(self):
        """
        Reset global breadcrumb state before each test method by clearing the agent logger's breadcrumb list.
        """
        _reset_breadcrumbs()

    def teardown_method(self):
        """
        Reset shared breadcrumb state after each test completes.
        """
        _reset_breadcrumbs()

    @pytest.mark.asyncio
    async def test_async_wrapper_pushes_and_pops_breadcrumb(self):
        """
        Verify that an async function decorated with `agent_trace` pushes a breadcrumb while running and pops it after completion.
        
        The test records the agent path from inside the decorated coroutine (expected "my_step") and asserts that the global agent path is an empty string after the coroutine finishes.
        """
        observed = []

        @agent_trace("my_step")
        async def capturing_func():
            """
            Append the current agent logger path to the enclosing `observed` list.
            
            This coroutine retrieves the current path from `agent_logger.get_path()` and appends it to the outer-scope list `observed`.
            """
            observed.append(agent_logger.get_path())

        await capturing_func()

        assert observed == ["my_step"]
        # After the call the breadcrumb must have been popped
        assert agent_logger.get_path() == ""

    def test_sync_wrapper_pushes_and_pops_breadcrumb(self):
        observed = []

        @agent_trace("sync_step")
        def capturing_func():
            """
            Record the current agent breadcrumb path into the enclosing `observed` list.
            
            Appends the value returned by `agent_logger.get_path()` to the surrounding scope's `observed` list as a side effect; does not return a value.
            """
            observed.append(agent_logger.get_path())

        capturing_func()

        assert observed == ["sync_step"]
        assert agent_logger.get_path() == ""

    @pytest.mark.asyncio
    async def test_nested_async_traces_build_path(self):
        observed = []

        @agent_trace("outer")
        async def outer():
            """
            Record the agent trace path observed inside a nested `inner` trace and then record the agent path after `inner` completes.
            
            The inner coroutine is decorated with `@agent_trace("inner")` and appends the current agent path to the `observed` list while running. After awaiting `inner()`, `outer` appends the current agent path again.
            """
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
            """
            Raise a ValueError with message "boom".
            
            Raises:
                ValueError: always raised with the message "boom".
            """
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            failing_func()

        assert agent_logger.get_path() == ""

    @pytest.mark.asyncio
    async def test_breadcrumb_popped_even_on_async_exception(self):
        @agent_trace("async_failing_step")
        async def failing_func():
            """
            Asynchronous test helper that always raises a RuntimeError.
            
            Raises:
                RuntimeError: Always raised with message "async boom".
            """
            raise RuntimeError("async boom")

        with pytest.raises(RuntimeError, match="async boom"):
            await failing_func()

        assert agent_logger.get_path() == ""


# ---------------------------------------------------------------------------
# Exception path annotation
# ---------------------------------------------------------------------------

class TestAgentTraceExceptionPath:
    def setup_method(self):
        """
        Reset global breadcrumb state before each test method by clearing the agent logger's breadcrumb list.
        """
        _reset_breadcrumbs()

    def teardown_method(self):
        """
        Reset shared breadcrumb state after each test completes.
        """
        _reset_breadcrumbs()

    def test_sync_exception_receives_agent_path_attribute(self):
        @agent_trace("annotated_step")
        def broken():
            """
            Always raises a ValueError with the message "broken".
            
            Raises:
                ValueError: always raised with message "broken".
            """
            raise ValueError("broken")

        try:
            broken()
        except ValueError as exc:
            assert hasattr(exc, "__agent_path__")
            assert "annotated_step" in exc.__agent_path__

    @pytest.mark.asyncio
    async def test_async_exception_receives_agent_path_attribute(self):
        """
        Verifies that an exception raised inside an async function decorated with `agent_trace` is annotated with a `__agent_path__` attribute.
        
        Asserts the exception object has a `__agent_path__` attribute and that it contains the decorator step name `async_annotated`.
        """
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
            """
            Defines and calls an inner traced function that raises a ValueError with a pre-set `__agent_path__`.
            
            The inner function sets `err.__agent_path__ = "already_set"` and then raises the error, causing `outer` to propagate that exception.
            """
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
            """
            Placeholder function used by tests as a no-op target for decorator and metadata-preservation checks.
            
            This function intentionally performs no operation and exists to verify decorator behavior (e.g., metadata preservation, async/sync detection) in unit tests.
            """
            pass

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "My docstring."

    @pytest.mark.asyncio
    async def test_async_wrapper_preserves_function_metadata(self):
        @agent_trace("async_meta_step")
        async def async_documented_func():
            """
            No-op asynchronous function used as a placeholder in tests.
            
            This coroutine performs no actions and returns None; it exists to exercise
            async code paths and decorator behavior in unit tests.
            """
            pass

        assert async_documented_func.__name__ == "async_documented_func"
        assert async_documented_func.__doc__ == "Async docstring."