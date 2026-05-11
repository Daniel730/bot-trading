import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import mcp_server


@pytest.mark.asyncio
async def test_mcp_execute_trade_rejects_or_uses_safe_ledger_payload(monkeypatch):
    direct_execute = AsyncMock(
        return_value=SimpleNamespace(status=0, message="accepted", actual_vwap=123.45)
    )
    log_trade = AsyncMock()
    monkeypatch.setattr(mcp_server.execution_client, "execute_trade", direct_execute)
    monkeypatch.setattr(mcp_server.persistence_service, "log_trade", log_trade)

    result = json.loads(
        await mcp_server.execute_trade(
            ticker="AAPL",
            side="BUY",
            quantity=1.0,
            mode="SHADOW",
            pair_id="AAPL_MSFT",
        )
    )

    assert result["status"] == "rejected"
    assert "disabled" in result["reason"].lower()
    direct_execute.assert_not_awaited()
    log_trade.assert_not_awaited()
