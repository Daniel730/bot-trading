"""Optional FastMCP SSE tool server.

Security model (defense in depth with compose loopback publishes):
- Process bind defaults to 127.0.0.1; non-loopback requires MCP_ALLOW_NON_LOOPBACK=true
  (Docker sets this so the container can listen on 0.0.0.0 while the host publish stays
  127.0.0.1:8000:8000).
- execute_trade always rejects; no brokerage / gRPC / ledger imports on this module.
- Optional MCP_TOOL_TOKEN: when set, every tool requires a matching auth_token argument.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from fastmcp import FastMCP

from src.services.redis_service import redis_service

mcp = FastMCP("Arbitrage-Elite-Engine")

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUTHY


def resolve_mcp_bind(
    host: Optional[str] = None,
    *,
    allow_non_loopback: Optional[bool] = None,
) -> tuple[str, int]:
    """Resolve listen host/port; refuse accidental all-interfaces binds."""
    bind_host = (host if host is not None else os.getenv("MCP_HOST", "127.0.0.1")).strip()
    if not bind_host:
        bind_host = "127.0.0.1"

    port_raw = os.getenv("MCP_PORT", "8000").strip() or "8000"
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(f"MCP_PORT must be an integer, got {port_raw!r}") from exc
    if not (1 <= port <= 65535):
        raise ValueError(f"MCP_PORT out of range: {port}")

    allowed = (
        allow_non_loopback
        if allow_non_loopback is not None
        else _env_flag("MCP_ALLOW_NON_LOOPBACK")
    )
    if bind_host not in _LOOPBACK_HOSTS and not allowed:
        raise RuntimeError(
            f"Refusing MCP bind to {bind_host!r}: set MCP_HOST=127.0.0.1 "
            "or explicitly MCP_ALLOW_NON_LOOPBACK=true (Docker only; keep "
            "compose host publish on 127.0.0.1)."
        )
    return bind_host, port


def _configured_tool_token() -> str:
    return os.getenv("MCP_TOOL_TOKEN", "").strip()


def _auth_rejection(auth_token: Optional[str]) -> Optional[dict]:
    """Fail closed when MCP_TOOL_TOKEN is configured and the caller token mismatches."""
    expected = _configured_tool_token()
    if not expected:
        return None
    provided = (auth_token or "").strip()
    if provided and provided == expected:
        return None
    return {
        "status": "rejected",
        "reason": "unauthorized: MCP_TOOL_TOKEN required via auth_token",
    }


@mcp.tool()
async def get_market_data(
    tickers: List[str],
    source: str = "redis",
    lookback: str = "30d",
    auth_token: str = "",
) -> str:
    """
    Fetches latest Redis shadow-book prices for tickers (read-only; no broker).
    """
    denied = _auth_rejection(auth_token)
    if denied:
        return json.dumps(denied)

    # Cap list size so a misbehaving client cannot fan out Redis reads.
    capped = list(tickers or [])[:32]
    prices: Dict[str, float] = {}
    for ticker in capped:
        if not isinstance(ticker, str) or not ticker.strip():
            continue
        price = await redis_service.get_price(ticker.strip())
        if price is not None:
            prices[ticker.strip()] = price

    return json.dumps(
        {
            "status": "success",
            "prices": prices,
            # Redis only — never route to brokerage or live order APIs from MCP.
            "source": "redis",
            "requested_source": source,
            "lookback_ignored": lookback,
        }
    )


@mcp.tool()
async def execute_trade(
    ticker: str,
    side: str,
    quantity: float,
    mode: str = "SHADOW",
    pair_id: str = "MANUAL",
    auth_token: str = "",
) -> str:
    """
    Rejects direct FastMCP trade execution until it can share the main bot safety path.
    """
    # Auth mismatch still returns rejected — never open a broker path either way.
    denied = _auth_rejection(auth_token)
    if denied:
        denied.update(
            {
                "mode": mode,
                "pair_id": pair_id,
                "ticker": ticker,
                "side": side,
                "quantity": quantity,
            }
        )
        return json.dumps(denied)

    return json.dumps(
        {
            "status": "rejected",
            "reason": (
                "FastMCP execute_trade is disabled; use the dashboard/monitor "
                "execution workflow so paper/live, risk, and reconciliation gates run."
            ),
            "mode": mode,
            "pair_id": pair_id,
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
        }
    )


@mcp.tool()
async def calculate_risk_metrics(
    confidence_score: float,
    portfolio: List[Dict] = None,
    auth_token: str = "",
) -> str:
    """
    Computes placeholder position sizing and VaR (no broker or portfolio mutation).
    """
    denied = _auth_rejection(auth_token)
    if denied:
        return json.dumps(denied)

    # Implementation placeholder for T009 — deliberately non-mutating.
    _ = (confidence_score, portfolio)
    return json.dumps({"suggested_size": 10.0, "var_95": 0.015, "status": "success"})


if __name__ == "__main__":
    bind_host, bind_port = resolve_mcp_bind()
    mcp.run(transport="sse", host=bind_host, port=bind_port)
