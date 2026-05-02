"""
Tests for the PR changes to src/services/web3_service.py:

- get_account_cash renamed to get_account_balance
- get_budget_snapshot now calls get_account_balance (not get_account_cash)
- get_account_balance returns 0.0 when w3 or account is unavailable
- get_account_balance returns 0.0 on exception
- get_budget_snapshot returns error dict when account not configured
- get_budget_snapshot returns error dict when Web3 is not enabled
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_web3_service(
    *,
    w3_available: bool = True,
    account_available: bool = True,
    enabled: bool = True,
):
    """
    Import Web3BrokerageService and configure its internal state with mocks so
    the service can be tested without real Web3 / Alchemy credentials.
    """
    from src.services.web3_service import Web3BrokerageService

    svc = Web3BrokerageService.__new__(Web3BrokerageService)
    svc.enabled = enabled
    svc.w3 = MagicMock() if w3_available else None
    svc.account = MagicMock() if account_available else None
    if account_available:
        svc.account.address = "0xDeadBeef"
    return svc


# ---------------------------------------------------------------------------
# get_account_balance – renamed from get_account_cash
# ---------------------------------------------------------------------------

class TestGetAccountBalance:
    @pytest.mark.asyncio
    async def test_method_is_named_get_account_balance(self):
        """The PR renamed get_account_cash → get_account_balance."""
        from src.services.web3_service import Web3BrokerageService
        assert hasattr(Web3BrokerageService, "get_account_balance")

    @pytest.mark.asyncio
    async def test_old_method_get_account_cash_does_not_exist(self):
        """Verify the old name was removed."""
        from src.services.web3_service import Web3BrokerageService
        assert not hasattr(Web3BrokerageService, "get_account_cash")

    @pytest.mark.asyncio
    async def test_returns_zero_when_w3_is_none(self):
        svc = _make_web3_service(w3_available=False)
        result = await svc.get_account_balance()
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_returns_zero_when_account_is_none(self):
        svc = _make_web3_service(account_available=False)
        result = await svc.get_account_balance()
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_returns_float_balance_from_w3(self):
        svc = _make_web3_service()
        # Simulate w3.eth.get_balance returning 2e18 wei (= 2 ETH)
        svc.w3.eth.get_balance.return_value = 2_000_000_000_000_000_000
        svc.w3.from_wei.return_value = 2.0

        result = await svc.get_account_balance()

        assert result == 2.0
        svc.w3.eth.get_balance.assert_called_once_with("0xDeadBeef")
        svc.w3.from_wei.assert_called_once_with(2_000_000_000_000_000_000, "ether")

    @pytest.mark.asyncio
    async def test_returns_zero_on_exception(self):
        svc = _make_web3_service()
        svc.w3.eth.get_balance.side_effect = RuntimeError("RPC error")

        result = await svc.get_account_balance()

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_returns_zero_balance_when_eth_balance_is_zero(self):
        svc = _make_web3_service()
        svc.w3.eth.get_balance.return_value = 0
        svc.w3.from_wei.return_value = 0.0

        result = await svc.get_account_balance()
        assert result == 0.0


# ---------------------------------------------------------------------------
# get_budget_snapshot – now calls get_account_balance (PR change)
# ---------------------------------------------------------------------------

class TestGetBudgetSnapshot:
    @pytest.mark.asyncio
    async def test_returns_error_when_account_not_configured(self):
        svc = _make_web3_service(account_available=False)

        result = await svc.get_budget_snapshot()

        assert result["status"] == "error"
        assert "not configured" in result["message"].lower()
        assert result["available_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_returns_error_when_web3_not_enabled(self):
        svc = _make_web3_service(enabled=False)

        result = await svc.get_budget_snapshot()

        assert result["status"] == "error"
        assert "not enabled" in result["message"].lower()
        assert result["available_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_success_calls_get_account_balance(self):
        """
        get_budget_snapshot must call get_account_balance (not the old
        get_account_cash) after the PR rename.
        """
        svc = _make_web3_service()

        # Patch get_account_balance and get_base_token_price_usd on the instance
        svc.get_account_balance = AsyncMock(return_value=1.5)
        svc.get_base_token_price_usd = AsyncMock(return_value=3000.0)

        with patch("src.services.web3_service.settings") as mock_settings:
            mock_settings.WEB3_BASE_TOKEN_SYMBOL = "ETH"
            result = await svc.get_budget_snapshot()

        svc.get_account_balance.assert_awaited_once()
        assert result["status"] == "success"
        assert result["base_units"] == 1.5
        assert result["price_usd"] == 3000.0
        assert result["balance_usd"] == pytest.approx(4500.0)
        assert result["available_usd"] == pytest.approx(4500.0)
        assert result["source"] == "web3_balance_x_price"

    @pytest.mark.asyncio
    async def test_success_result_includes_base_symbol(self):
        svc = _make_web3_service()
        svc.get_account_balance = AsyncMock(return_value=0.5)
        svc.get_base_token_price_usd = AsyncMock(return_value=2000.0)

        with patch("src.services.web3_service.settings") as mock_settings:
            mock_settings.WEB3_BASE_TOKEN_SYMBOL = "ETH"
            result = await svc.get_budget_snapshot()

        assert result["base_symbol"] == "ETH"

    @pytest.mark.asyncio
    async def test_returns_error_on_exception_in_get_budget_snapshot(self):
        svc = _make_web3_service()
        svc.get_account_balance = AsyncMock(side_effect=RuntimeError("balance fetch failed"))
        svc.get_base_token_price_usd = AsyncMock(return_value=2000.0)

        result = await svc.get_budget_snapshot()

        assert result["status"] == "error"
        assert result["available_usd"] == 0.0
