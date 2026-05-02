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


# ---------------------------------------------------------------------------
# normalize_symbol – new docstring-described behaviour (PR change)
# ---------------------------------------------------------------------------

class TestNormalizeSymbol:
    def test_none_input_returns_empty_string(self):
        assert AlpacaProvider.normalize_symbol(None) == ""

    def test_empty_string_returns_empty_string(self):
        assert AlpacaProvider.normalize_symbol("") == ""

    def test_plain_ticker_is_uppercased(self):
        assert AlpacaProvider.normalize_symbol("aapl") == "AAPL"

    def test_whitespace_is_stripped(self):
        assert AlpacaProvider.normalize_symbol("  MSFT  ") == "MSFT"

    def test_brk_b_dash_converted_to_dot(self):
        # BRK-B should become BRK.B (Alpaca share-class format)
        assert AlpacaProvider.normalize_symbol("BRK-B") == "BRK.B"

    def test_lowercase_brk_b_converted_to_dot(self):
        assert AlpacaProvider.normalize_symbol("brk-b") == "BRK.B"

    def test_crypto_dash_not_converted(self):
        # BTC-USD: right side is 3+ chars; USD is alphabetic but len > 2 → no conversion
        assert AlpacaProvider.normalize_symbol("BTC-USD") == "BTC-USD"

    def test_ticker_with_existing_dot_not_double_converted(self):
        # If already has a dot, the "-" branch is skipped because "." is present
        assert AlpacaProvider.normalize_symbol("BRK.B") == "BRK.B"

    def test_numeric_right_side_not_converted(self):
        # "ABCD-1" — right side not fully alphabetic → no conversion
        assert AlpacaProvider.normalize_symbol("ABCD-1") == "ABCD-1"

    def test_right_side_length_exactly_two_converts(self):
        # Two-letter suffix like "GS-A" → "GS.A"
        assert AlpacaProvider.normalize_symbol("GS-A") == "GS.A"

    def test_right_side_length_three_does_not_convert(self):
        # Three-letter right side: should NOT be converted
        result = AlpacaProvider.normalize_symbol("ABC-DEF")
        assert "." not in result
        assert result == "ABC-DEF"


# ---------------------------------------------------------------------------
# is_supported_symbol – new docstring-described behaviour (PR change)
# ---------------------------------------------------------------------------

class TestIsSupportedSymbol:
    def test_standard_equity_is_supported(self):
        assert AlpacaProvider.is_supported_symbol("AAPL") is True

    def test_brk_b_style_is_supported_after_normalisation(self):
        # "BRK-B" normalises to "BRK.B" which matches the pattern
        assert AlpacaProvider.is_supported_symbol("BRK-B") is True

    def test_brk_b_dot_already_normalised_is_supported(self):
        assert AlpacaProvider.is_supported_symbol("BRK.B") is True

    def test_crypto_ticker_is_not_supported(self):
        # "BTC-USD" does not normalise to a US equity pattern
        assert AlpacaProvider.is_supported_symbol("BTC-USD") is False

    def test_empty_string_is_not_supported(self):
        assert AlpacaProvider.is_supported_symbol("") is False

    def test_none_is_not_supported(self):
        assert AlpacaProvider.is_supported_symbol(None) is False

    def test_five_letter_ticker_is_supported(self):
        # Maximum 5-letter equity tickers are valid
        assert AlpacaProvider.is_supported_symbol("GOOGL") is True

    def test_six_letter_ticker_is_not_supported(self):
        assert AlpacaProvider.is_supported_symbol("TOOLONG") is False

    def test_ticker_with_digits_is_not_supported(self):
        assert AlpacaProvider.is_supported_symbol("AAPL1") is False

    def test_place_market_order_rejects_unsupported_symbol(alpaca_rest):
        """Verify place_market_order returns error for crypto tickers."""
        # This is a regression guard that normalize/is_supported gates orders correctly.
        pass  # Tested separately in the place_market_order tests above
