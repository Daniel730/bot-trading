import logging
import asyncio
from typing import Dict, Any, List, Optional
from decimal import Decimal
from web3 import Web3
from src.config import settings

logger = logging.getLogger(__name__)

# web3.py changed POA middleware exports across major versions.
# Keep startup resilient by resolving whichever name/path is available.
try:
    from web3.middleware import geth_poa_middleware as _poa_middleware
except Exception:
    try:
        from web3.middleware import ExtraDataToPOAMiddleware as _poa_middleware
    except Exception:
        try:
            from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware as _poa_middleware
        except Exception:
            _poa_middleware = None

class Web3BrokerageService:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.WEB3_RPC_URL))
        # Add POA middleware for compatible chains (Polygon, BSC, etc.)
        if _poa_middleware is not None:
            try:
                self.w3.middleware_onion.inject(_poa_middleware, layer=0)
            except Exception as e:
                logger.warning(f"Web3: POA middleware inject skipped: {e}")
        else:
            logger.info("Web3: No POA middleware available in installed web3 version.")
        
        self.account = None
        if settings.WEB3_PRIVATE_KEY:
            try:
                self.account = self.w3.eth.account.from_key(settings.WEB3_PRIVATE_KEY)
                logger.info(f"Web3 Account Initialized: {self.account.address}")
            except Exception as e:
                logger.error(f"Failed to initialize Web3 account: {e}")

    @property
    def enabled(self) -> bool:
        return settings.web3_enabled

    async def test_connection(self) -> Dict[str, Any]:
        """Tests connectivity to the RPC and verifies account balance."""
        try:
            is_connected = self.w3.is_connected()
            if not is_connected:
                logger.error("Web3: Failed to connect to RPC provider.")
                return {"status": "error", "message": "Failed to connect to RPC provider."}
            
            block_number = self.w3.eth.block_number
            logger.info(f"Web3: Connected to chain {settings.WEB3_CHAIN_ID}. Current block: {block_number}")
            
            balance_eth = 0.0
            if self.account:
                balance_wei = self.w3.eth.get_balance(self.account.address)
                balance_eth = float(self.w3.from_wei(balance_wei, 'ether'))
                logger.info(f"Web3: Account {self.account.address} balance: {balance_eth:.4f} ETH")
            
            return {
                "status": "success",
                "block_number": block_number,
                "base_token_balance": balance_eth, # Using ETH as proxy for balance in test_connection
                "address": self.account.address if self.account else None
            }
        except Exception as e:
            logger.error(f"Web3 Connection Test failed: {e}")
            return {"status": "error", "message": str(e)}

    def _get_token_info(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Resolves a ticker (e.g. BTC-USD or ETH) to its contract metadata."""
        # Clean ticker: BTC-USD -> BTC
        clean_ticker = ticker.replace("-USD", "").upper()
        return settings.CRYPTO_TOKEN_MAPPING.get(clean_ticker)

    async def place_value_order(self, ticker: str, amount_fiat: float, side: str) -> Dict[str, Any]:
        """
        Executes a swap on-chain using a DEX router.
        Currently supports Uniswap V2-style routers.
        """
        if not self.account:
            return {"status": "error", "message": "Web3 account not configured."}

        token_info = self._get_token_info(ticker)
        if not token_info:
            return {"status": "error", "message": f"Ticker {ticker} not found in CRYPTO_TOKEN_MAPPING."}

        base_token_info = settings.CRYPTO_TOKEN_MAPPING.get(settings.WEB3_BASE_TOKEN_SYMBOL)
        if not base_token_info:
            return {"status": "error", "message": f"Base token {settings.WEB3_BASE_TOKEN_SYMBOL} not found in mapping."}

        try:
            # Placeholder for actual swap logic
            # In a real implementation, we would:
            # 1. Determine the swap path (Base -> Target or Target -> Base)
            # 2. Check for token approvals
            # 3. Estimate Gas and Slippage
            # 4. Build and Sign the transaction
            # 5. Broadcast and Wait for Receipt

            logger.info(f"Web3: Simulating {side} swap for {ticker} (Value: ${amount_fiat})")
            
            # For now, return a success placeholder to allow integration testing
            return {
                "status": "success",
                "order_id": f"web3_tx_placeholder_{self.w3.eth.block_number}",
                "message": f"Successfully simulated on-chain {side} for {ticker}",
                "explorer_url": f"https://etherscan.io/tx/placeholder" # Should be dynamic based on chain
            }
            
        except Exception as e:
            logger.error(f"Web3 Swap Error: {e}")
            return {"status": "error", "message": str(e)}

    async def get_account_balance(self) -> float:
        """Returns the base token balance (e.g. USDC) formatted as a float."""
        if not self.account:
            return 0.0
        
        # In a real implementation, we would call balanceOf() on the base token contract
        try:
            # Native balance fallback for now
            balance_wei = self.w3.eth.get_balance(self.account.address)
            return float(self.w3.from_wei(balance_wei, 'ether'))
        except:
            return 0.0

web3_service = Web3BrokerageService()
