import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import mcp_server

ROOT = Path(__file__).resolve().parents[2]
MCP_SOURCE = ROOT / "src" / "mcp_server.py"
BACKEND_COMPOSE = ROOT / "infra" / "docker-compose.backend.yml"


async def _call_mcp_tool(tool, **kwargs):
    """Invoke a FastMCP-registered tool across FastMCP 2.x (FunctionTool.fn) and 3.x."""
    fn = getattr(tool, "fn", None) or getattr(tool, "function", None) or tool
    return await fn(**kwargs)


@pytest.mark.asyncio
async def test_mcp_execute_trade_rejects_or_uses_safe_ledger_payload(monkeypatch):
    # Module must not even expose these; if a regression re-imports them, still
    # prove the tool never awaits broker/ledger side effects.
    monkeypatch.setenv("MCP_TOOL_TOKEN", "expected-secret")
    direct_execute = AsyncMock(
        return_value=SimpleNamespace(status=0, message="accepted", actual_vwap=123.45)
    )
    log_trade = AsyncMock()
    if hasattr(mcp_server, "execution_client"):
        monkeypatch.setattr(mcp_server.execution_client, "execute_trade", direct_execute)
    if hasattr(mcp_server, "persistence_service"):
        monkeypatch.setattr(mcp_server.persistence_service, "log_trade", log_trade)

    result = json.loads(
        await _call_mcp_tool(
            mcp_server.execute_trade,
            ticker="AAPL",
            side="BUY",
            quantity=1.0,
            mode="SHADOW",
            pair_id="AAPL_MSFT",
            auth_token="expected-secret",
        )
    )

    assert result["status"] == "rejected"
    assert "disabled" in result["reason"].lower()
    direct_execute.assert_not_awaited()
    log_trade.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["SHADOW", "LIVE", "PAPER", "BROKER"])
async def test_mcp_execute_trade_rejects_all_modes(mode: str, monkeypatch):
    monkeypatch.setenv("MCP_TOOL_TOKEN", "expected-secret")
    result = json.loads(
        await _call_mcp_tool(
            mcp_server.execute_trade,
            ticker="BTC-USD",
            side="SELL",
            quantity=0.5,
            mode=mode,
            pair_id="MANUAL",
            auth_token="expected-secret",
        )
    )
    assert result["status"] == "rejected"
    assert result["mode"] == mode
    assert "disabled" in result["reason"].lower()


@pytest.mark.asyncio
async def test_mcp_execute_trade_auth_mismatch_still_rejects_without_broker(monkeypatch):
    monkeypatch.setenv("MCP_TOOL_TOKEN", "expected-secret")
    result = json.loads(
        await _call_mcp_tool(
            mcp_server.execute_trade,
            ticker="AAPL",
            side="BUY",
            quantity=1.0,
            mode="LIVE",
            auth_token="wrong",
        )
    )
    assert result["status"] == "rejected"
    assert "unauthorized" in result["reason"].lower()


@pytest.mark.asyncio
async def test_mcp_get_market_data_requires_token_when_configured(monkeypatch):
    monkeypatch.setenv("MCP_TOOL_TOKEN", "expected-secret")
    get_price = AsyncMock(return_value=101.0)
    monkeypatch.setattr(mcp_server.redis_service, "get_price", get_price)

    denied = json.loads(await _call_mcp_tool(mcp_server.get_market_data, tickers=["AAPL"]))
    assert denied["status"] == "rejected"
    get_price.assert_not_awaited()

    ok = json.loads(
        await _call_mcp_tool(
            mcp_server.get_market_data,
            tickers=["AAPL"],
            auth_token="expected-secret",
        )
    )
    assert ok["status"] == "success"
    assert ok["prices"]["AAPL"] == 101.0
    assert ok["source"] == "redis"
    get_price.assert_awaited_once_with("AAPL")


@pytest.mark.asyncio
async def test_mcp_get_market_data_requires_configured_token(monkeypatch):
    """F-008: unset/placeholder MCP_TOOL_TOKEN must fail closed."""
    monkeypatch.delenv("MCP_TOOL_TOKEN", raising=False)
    get_price = AsyncMock(return_value=42.0)
    monkeypatch.setattr(mcp_server.redis_service, "get_price", get_price)

    denied = json.loads(await _call_mcp_tool(mcp_server.get_market_data, tickers=["MSFT"]))
    assert denied["status"] == "rejected"
    assert "not configured" in denied["reason"]
    get_price.assert_not_awaited()

    monkeypatch.setenv("MCP_TOOL_TOKEN", "expected-secret")
    ok = json.loads(
        await _call_mcp_tool(
            mcp_server.get_market_data,
            tickers=["MSFT"],
            source="alpaca",
            auth_token="expected-secret",
        )
    )
    assert ok["status"] == "success"
    assert ok["source"] == "redis"
    assert ok["requested_source"] == "alpaca"
    get_price.assert_awaited_once_with("MSFT")


@pytest.mark.asyncio
async def test_mcp_get_market_data_never_claims_broker_source(monkeypatch):
    monkeypatch.setenv("MCP_TOOL_TOKEN", "expected-secret")
    monkeypatch.setattr(
        mcp_server.redis_service, "get_price", AsyncMock(return_value=42.0)
    )
    result = json.loads(
        await _call_mcp_tool(
            mcp_server.get_market_data,
            tickers=["MSFT"],
            source="alpaca",
            auth_token="expected-secret",
        )
    )
    assert result["status"] == "success"
    assert result["source"] == "redis"
    assert result["requested_source"] == "alpaca"


def test_resolve_mcp_bind_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv("MCP_HOST", raising=False)
    monkeypatch.delenv("MCP_PORT", raising=False)
    monkeypatch.delenv("MCP_ALLOW_NON_LOOPBACK", raising=False)
    host, port = mcp_server.resolve_mcp_bind()
    assert host == "127.0.0.1"
    assert port == 8000


def test_resolve_mcp_bind_refuses_public_without_allow(monkeypatch):
    monkeypatch.delenv("MCP_ALLOW_NON_LOOPBACK", raising=False)
    with pytest.raises(RuntimeError, match="MCP_ALLOW_NON_LOOPBACK"):
        mcp_server.resolve_mcp_bind(host="0.0.0.0", allow_non_loopback=False)


def test_resolve_mcp_bind_allows_docker_all_interfaces(monkeypatch):
    monkeypatch.setenv("MCP_ALLOW_NON_LOOPBACK", "true")
    host, port = mcp_server.resolve_mcp_bind(host="0.0.0.0")
    assert host == "0.0.0.0"
    assert port == 8000


def test_mcp_module_has_no_broker_or_execution_imports():
    tree = ast.parse(MCP_SOURCE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imported.add(mod)
            for alias in node.names:
                imported.add(f"{mod}.{alias.name}" if mod else alias.name)

    banned_substrings = (
        "execution_service_client",
        "execution_client",
        "brokerage",
        "persistence_service",
        "OrderSide",
        "shadow_service",
        "alpaca",
    )
    joined = "\n".join(sorted(imported))
    for banned in banned_substrings:
        assert banned not in joined, f"unexpected import involving {banned!r}: {joined}"

    source = MCP_SOURCE.read_text(encoding="utf-8")
    assert "from src.services.redis_service import redis_service" in source
    assert "FastMCP execute_trade is disabled" in source
    tool_body = source.split("async def execute_trade", 1)[1].split("@mcp.tool()", 1)[0]
    assert "execution_client" not in tool_body
    assert "brokerage" not in tool_body.lower()
    assert "log_trade" not in tool_body


def test_compose_mcp_explicit_container_bind_with_loopback_publish():
    text = BACKEND_COMPOSE.read_text(encoding="utf-8")
    assert '"127.0.0.1:8000:8000"' in text
    assert 'MCP_HOST: "0.0.0.0"' in text
    assert 'MCP_ALLOW_NON_LOOPBACK: "true"' in text
