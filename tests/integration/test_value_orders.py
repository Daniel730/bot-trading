import pytest
from src.services.risk_service import risk_service
from src.services.brokerage.alpaca import AlpacaProvider
from types import SimpleNamespace
from unittest.mock import patch

@pytest.mark.asyncio
async def test_value_order_flow_success_uses_alpaca_notional_buy():
    with patch("src.services.brokerage.alpaca.tradeapi.REST") as rest_cls:
        client = rest_cls.return_value
        client.list_assets.return_value = [SimpleNamespace(symbol="AAPL")]
        client.submit_order.return_value = SimpleNamespace(id="12345", client_order_id=None)
        provider = AlpacaProvider(api_key="key", api_secret="secret", base_url="url")

        result = await provider.place_value_order("AAPL", 15.0, "BUY")

    assert result["status"] == "success"
    client.submit_order.assert_called_once_with(
        symbol="AAPL",
        notional=15.0,
        side="buy",
        type="market",
        time_in_force="day",
    )

def test_value_order_fee_rejection():
    # We test the logic in monitor.py integration via risk_service
    # If $0.50 trade is attempted, it should be rejected by risk_service

    amount = 0.50
    check = risk_service.is_trade_allowed(amount, 0.01) # 1% friction
    assert check['allowed'] == False
    assert "below minimum" in check['reason']

    # High friction case
    amount = 10.0
    check = risk_service.is_trade_allowed(amount, 0.05) # 5% friction
    assert check['allowed'] == False
    assert "exceeds limit" in check['reason']
