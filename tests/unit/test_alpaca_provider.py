from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import pytest

from src.services.brokerage.alpaca import AlpacaProvider


def _order(order_id="ord-1", client_order_id="client-1"):
    return SimpleNamespace(id=order_id, client_order_id=client_order_id)


@pytest.fixture
def alpaca_rest():
    with patch("src.services.brokerage.alpaca.tradeapi.REST") as rest_cls:
        yield rest_cls, rest_cls.return_value


def test_alpaca_provider_initializes_rest_client(alpaca_rest):
    rest_cls, _ = alpaca_rest

    AlpacaProvider(
        api_key="paper-key",
        api_secret="paper-secret",
        base_url="https://paper-api.alpaca.markets",
    )

    rest_cls.assert_called_once_with(
        "paper-key",
        "paper-secret",
        "https://paper-api.alpaca.markets",
        api_version="v2",
    )


def test_alpaca_connection_uses_account_probe(alpaca_rest):
    _, client = alpaca_rest
    provider = AlpacaProvider(api_key="key", api_secret="secret", base_url="url")

    assert provider.test_connection() is True
    client.get_account.assert_called_once()

    client.get_account.side_effect = RuntimeError("bad credentials")
    assert provider.test_connection() is False


@pytest.mark.asyncio
async def test_place_market_order_submits_alpaca_market_payload(alpaca_rest):
    _, client = alpaca_rest
    client.submit_order.return_value = _order("ord-market", "cid-market")
    provider = AlpacaProvider(api_key="key", api_secret="secret", base_url="url")

    result = await provider.place_market_order(
        "AAPL",
        1.25,
        "BUY",
        client_order_id="cid-market",
    )

    assert result == {
        "status": "success",
        "order_id": "ord-market",
        "broker": "ALPACA",
        "client_order_id": "cid-market",
    }
    client.submit_order.assert_called_once_with(
        symbol="AAPL",
        qty=1.25,
        side="buy",
        type="market",
        time_in_force="day",
        client_order_id="cid-market",
    )


@pytest.mark.asyncio
async def test_place_market_order_submits_alpaca_limit_payload(alpaca_rest):
    _, client = alpaca_rest
    client.submit_order.return_value = _order("ord-limit", "cid-limit")
    provider = AlpacaProvider(api_key="key", api_secret="secret", base_url="url")

    result = await provider.place_market_order(
        "MSFT",
        2.0,
        "SELL",
        limit_price=410.25,
        client_order_id="cid-limit",
    )

    assert result["order_id"] == "ord-limit"
    client.submit_order.assert_called_once_with(
        symbol="MSFT",
        qty=2.0,
        side="sell",
        type="limit",
        time_in_force="day",
        limit_price=410.25,
        client_order_id="cid-limit",
    )


@pytest.mark.asyncio
async def test_place_value_order_uses_alpaca_notional_orders(alpaca_rest):
    _, client = alpaca_rest
    client.submit_order.return_value = _order("ord-notional", "cid-value")
    provider = AlpacaProvider(api_key="key", api_secret="secret", base_url="url")

    result = await provider.place_value_order(
        "NVDA",
        250.0,
        "BUY",
        client_order_id="cid-value",
    )

    assert result == {
        "status": "success",
        "order_id": "ord-notional",
        "broker": "ALPACA",
        "client_order_id": "cid-value",
    }
    client.submit_order.assert_called_once_with(
        symbol="NVDA",
        notional=250.0,
        side="buy",
        type="market",
        time_in_force="day",
        client_order_id="cid-value",
    )


@pytest.mark.asyncio
async def test_place_value_order_falls_back_to_quantity_when_notional_fails(alpaca_rest):
    _, client = alpaca_rest
    client.submit_order.side_effect = [
        RuntimeError("notional unsupported"),
        _order("ord-qty", "cid-fallback"),
    ]
    provider = AlpacaProvider(api_key="key", api_secret="secret", base_url="url")

    with patch(
        "src.services.data_service.data_service.get_latest_price_async",
        new_callable=AsyncMock,
    ) as mock_price:
        mock_price.return_value = {"NVDA": 50.0}

        result = await provider.place_value_order(
            "NVDA",
            125.0,
            "BUY",
            client_order_id="cid-fallback",
        )

    assert result["order_id"] == "ord-qty"
    assert client.submit_order.call_args_list == [
        call(
            symbol="NVDA",
            notional=125.0,
            side="buy",
            type="market",
            time_in_force="day",
            client_order_id="cid-fallback",
        ),
        call(
            symbol="NVDA",
            qty=2.5,
            side="buy",
            type="market",
            time_in_force="day",
            client_order_id="cid-fallback",
        ),
    ]


@pytest.mark.asyncio
async def test_place_value_order_returns_error_when_fallback_price_is_invalid(alpaca_rest):
    _, client = alpaca_rest
    client.submit_order.side_effect = RuntimeError("notional unsupported")
    provider = AlpacaProvider(api_key="key", api_secret="secret", base_url="url")

    with patch(
        "src.services.data_service.data_service.get_latest_price_async",
        new_callable=AsyncMock,
    ) as mock_price:
        mock_price.return_value = {"NVDA": 0.0}

        result = await provider.place_value_order("NVDA", 125.0, "BUY")

    assert result == {"status": "error", "message": "Invalid price for NVDA fallback"}
    assert client.submit_order.call_count == 1


def test_alpaca_positions_are_normalized(alpaca_rest):
    _, client = alpaca_rest
    client.list_positions.return_value = [
        SimpleNamespace(
            symbol="AAPL",
            qty="3.5",
            qty_available="2.25",
            avg_entry_price="180.00",
            current_price="190.50",
            market_value="666.75",
        )
    ]
    provider = AlpacaProvider(api_key="key", api_secret="secret", base_url="url")

    assert provider.get_portfolio() == [
        {
            "ticker": "AAPL",
            "quantity": 3.5,
            "quantityAvailableForTrading": 2.25,
            "averagePrice": 180.0,
            "currentPrice": 190.5,
            "marketValue": 666.75,
        }
    ]


def test_alpaca_pending_orders_are_normalized(alpaca_rest):
    _, client = alpaca_rest
    client.list_orders.return_value = [
        SimpleNamespace(
            symbol="MSFT",
            qty="1.5",
            side="buy",
            status="accepted",
            limit_price="412.30",
            id="ord-open",
        )
    ]
    provider = AlpacaProvider(api_key="key", api_secret="secret", base_url="url")

    assert provider.get_pending_orders() == [
        {
            "ticker": "MSFT",
            "quantity": 1.5,
            "side": "BUY",
            "status": "accepted",
            "limitPrice": 412.3,
            "id": "ord-open",
        }
    ]
    client.list_orders.assert_called_once_with(status="open")


def test_alpaca_symbol_metadata_reflects_fractionable_asset(alpaca_rest):
    _, client = alpaca_rest
    client.get_asset.return_value = SimpleNamespace(
        symbol="AAPL",
        fractionable=True,
        status="active",
    )
    provider = AlpacaProvider(api_key="key", api_secret="secret", base_url="url")

    assert provider.get_symbol_metadata("AAPL") == {
        "ticker": "AAPL",
        "minTradeQuantity": 0.0001,
        "quantityIncrement": 0.0001,
        "tickSize": 0.01,
        "status": "active",
    }
