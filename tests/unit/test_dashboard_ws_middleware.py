"""Regression tests for DashboardAuthMiddleware handling of WebSocket scopes.

Previously the middleware built ``starlette.requests.Request(scope)`` for every
non-plain scope, but ``Request.__init__`` asserts ``scope["type"] == "http"``.
That crashed the ASGI app with ``AssertionError`` on every ``/ws/telemetry``
WebSocket handshake, spamming "Exception in ASGI application" and preventing
live telemetry over WebSocket. The middleware now uses ``HTTPConnection`` which
accepts both http and websocket scopes.
"""
import pytest

from src.services.dashboard_service import (
    DashboardAuthMiddleware,
    _dashboard_auth_session,
    _dashboard_auth_token,
)


def _make_scope(scope_type: str) -> dict:
    return {
        "type": scope_type,
        "headers": [
            (b"authorization", b"Bearer tok-123"),
            (b"x-dashboard-session", b"sess-abc"),
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("scope_type", ["websocket", "http"])
async def test_middleware_extracts_headers_without_crashing(scope_type):
    captured = {}

    async def app(scope, receive, send):
        captured["token"] = _dashboard_auth_token.get()
        captured["session"] = _dashboard_auth_session.get()

    async def receive():
        return {"type": f"{scope_type}.connect"}

    async def send(_message):
        return None

    middleware = DashboardAuthMiddleware(app)

    # Must not raise AssertionError for websocket scopes.
    await middleware(_make_scope(scope_type), receive, send)

    assert captured["token"] == "tok-123"
    assert captured["session"] == "sess-abc"
    # Context vars are reset after the request completes.
    assert _dashboard_auth_token.get() is None
    assert _dashboard_auth_session.get() is None


@pytest.mark.asyncio
async def test_middleware_passes_through_lifespan_scope():
    seen = {}

    async def app(scope, receive, send):
        seen["type"] = scope["type"]

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(_message):
        return None

    middleware = DashboardAuthMiddleware(app)
    await middleware({"type": "lifespan"}, receive, send)
    assert seen["type"] == "lifespan"
