import logging
import asyncio
from typing import Dict, Any, List, Optional
from src.config import settings

logger = logging.getLogger(__name__)

try:
    from web3 import Web3
except Exception:
    Web3 = None

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
        self.w3 = None
        if Web3 is None:
            logger.warning("Web3: python package 'web3' is not installed. Web3 execution disabled.")
            self.account = None
            return

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
                if not settings.WEB3_METAMASK_ADDRESS.strip():
                    logger.warning(
                        "WEB3_METAMASK_ADDRESS is empty. Broadcasts may not appear in your personal "
                        "MetaMask unless this signer wallet is imported there."
                    )
            except Exception as e:
                logger.error(f"Failed to initialize Web3 account: {e}")

    @property
    def enabled(self) -> bool:
        return bool(Web3 is not None and self.w3 is not None and settings.web3_enabled)

    @staticmethod
    def _explorer_base_url() -> str:
        chain_map = {
            1: "https://etherscan.io",
            11155111: "https://sepolia.etherscan.io",
        }
        return chain_map.get(settings.WEB3_CHAIN_ID, "https://etherscan.io")

    async def test_connection(self) -> Dict[str, Any]:
        """Tests connectivity to the RPC and verifies account balance."""
        if not self.w3:
            return {"status": "error", "message": "web3 package is not installed."}
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
                balance_eth = float(self.w3.from_wei(balance_wei, "ether"))
                logger.info(f"Web3: Account {self.account.address} balance: {balance_eth:.4f} ETH")

            return {
                "status": "success",
                "block_number": block_number,
                "base_token_balance": balance_eth,
                "address": self.account.address if self.account else None,
            }
        except Exception as e:
            logger.error(f"Web3 Connection Test failed: {e}")
            return {"status": "error", "message": str(e)}

    def _get_token_info(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Resolves a ticker (e.g. BTC-USD or ETH) to its contract metadata."""
        clean_ticker = ticker.replace("-USD", "").upper()
        return settings.CRYPTO_TOKEN_MAPPING.get(clean_ticker)

    # ------------------------------------------------------------------
    # Real Sepolia broadcast
    # ------------------------------------------------------------------

    def _broadcast_trade_signal(self, ticker: str, amount_fiat: float, side: str) -> Dict[str, Any]:
        """
        Broadcasts a zero-value ETH transfer on Sepolia encoding the trade
        signal in the transaction data field. Recipient is WEB3_METAMASK_ADDRESS
        when configured, otherwise the signer wallet (self-transfer).

        Memo format (UTF-8, hex-encoded in tx.data):
            ARBOT|BUY|BTC|USD123.45

        Gas price is clamped to WEB3_MAX_GAS_GWEI to prevent runaway costs on
        testnet spikes.  This is a synchronous call — invoke via asyncio.to_thread.
        """
        clean_ticker = ticker.replace("-USD", "").upper()
        memo = f"ARBOT|{side.upper()}|{clean_ticker}|USD{amount_fiat:.2f}"
        data_bytes = memo.encode("utf-8")

        # Gas price: use network suggestion, clamped to configured ceiling
        max_gas_wei = Web3.to_wei(settings.WEB3_MAX_GAS_GWEI, "gwei")
        try:
            suggested_gas_price = self.w3.eth.gas_price
        except Exception:
            suggested_gas_price = max_gas_wei
        gas_price = min(suggested_gas_price, max_gas_wei)

        nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")

        # If the user configured WEB3_METAMASK_ADDRESS, send the signal tx TO
        # that address so it appears in MetaMask activity.  Fall back to a
        # self-transfer (only visible in the bot's own wallet on Etherscan).
        metamask_addr = settings.WEB3_METAMASK_ADDRESS.strip()
        recipient = self.account.address
        if metamask_addr:
            try:
                recipient = Web3.to_checksum_address(metamask_addr)
            except Exception:
                logger.warning(
                    "WEB3_METAMASK_ADDRESS is invalid (%s). Falling back to signer wallet %s.",
                    metamask_addr, self.account.address
                )

        txn = {
            "chainId": settings.WEB3_CHAIN_ID,
            "to": recipient,
            "value": int(settings.WEB3_SIGNAL_VALUE_WEI),
            "gas": settings.WEB3_TX_GAS_LIMIT,
            "gasPrice": gas_price,
            "nonce": nonce,
            "data": data_bytes,
        }

        signed = self.account.sign_transaction(txn)

        # web3.py v5 uses .rawTransaction; v6 renamed it .raw_transaction
        raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)
        if raw_tx is None:
            raise RuntimeError("Could not extract raw transaction bytes from signed tx object.")

        tx_hash_bytes = self.w3.eth.send_raw_transaction(raw_tx)
        tx_hash_hex = tx_hash_bytes.hex()
        if not tx_hash_hex.startswith("0x"):
            tx_hash_hex = "0x" + tx_hash_hex

        explorer_url = f"{self._explorer_base_url()}/tx/{tx_hash_hex}"
        logger.info(
            f"WEB3 TX ROUTING: from={self.account.address} to={recipient} "
            f"chain={settings.WEB3_CHAIN_ID}"
        )
        logger.info(f"WEB3: Trade signal broadcast — {memo} | tx={tx_hash_hex} | {explorer_url}")
        return {
            "status": "success",
            "order_id": tx_hash_hex,
            "tx_hash": tx_hash_hex,
            "memo": memo,
            "from_address": self.account.address,
            "to_address": recipient,
            "explorer_url": explorer_url,
        }

    async def place_value_order(self, ticker: str, amount_fiat: float, side: str) -> Dict[str, Any]:
        """
        Executes a trade signal on-chain via a zero-value Sepolia transfer.
        The trade metadata is encoded in the transaction data field so it appears
        on Alchemy / Sepolia Etherscan (and in MetaMask if the receiving wallet
        is configured or imported there).
        """
        if not self.w3:
            return {"status": "error", "message": "web3 package is not installed."}

        if not self.account:
            return {"status": "error", "message": "Web3 account not configured."}

        token_info = self._get_token_info(ticker)
        if not token_info:
            clean_ticker = ticker.replace("-USD", "").upper()
            logger.warning(
                f"WEB3: {clean_ticker} not in CRYPTO_TOKEN_MAPPING — "
                f"proceeding with Sepolia broadcast (add contract address for mainnet DEX routing)."
            )
            token_info = {"address": "", "decimals": 18, "simulated": True}

        base_token_info = settings.CRYPTO_TOKEN_MAPPING.get(settings.WEB3_BASE_TOKEN_SYMBOL)
        if not base_token_info:
            logger.warning(
                f"WEB3: Base token {settings.WEB3_BASE_TOKEN_SYMBOL} not in CRYPTO_TOKEN_MAPPING — "
                f"proceeding with Sepolia broadcast."
            )
            base_token_info = {"address": "", "decimals": 6, "simulated": True}

        try:
            result = await asyncio.to_thread(
                self._broadcast_trade_signal, ticker, amount_fiat, side
            )
            return result
        except Exception as e:
            logger.error(f"Web3 broadcast error: {e}")
            return {"status": "error", "message": str(e)}

    async def get_account_cash(self) -> float:
        """Returns the native ETH balance as float.

        Used as a pragmatic proxy for spendable balance on Sepolia/Alchemy test
        setups where we hold ETH rather than a stablecoin base token.
        """
        if not self.w3 or not self.account:
            return 0.0
        try:
            balance_wei = self.w3.eth.get_balance(self.account.address)
            return float(self.w3.from_wei(balance_wei, "ether"))
        except Exception:
            return 0.0

    async def get_base_token_price_usd(self) -> float:
        """Returns WEB3_BASE_TOKEN_SYMBOL quoted in USD."""
        base_symbol = settings.WEB3_BASE_TOKEN_SYMBOL.upper().strip()
        stable_1usd = {"USD", "USDC", "USDT", "DAI", "FDUSD", "USDB", "PYUSD", "TUSD"}

        if base_symbol in stable_1usd:
            return 1.0

        # WETH should reuse ETH spot prices.
        spot_symbol = "ETH" if base_symbol == "WETH" else base_symbol
        spot_ticker = f"{spot_symbol}-USD"

        try:
            from src.services.data_service import data_service
            prices = await data_service.get_latest_price_async([spot_ticker])
            spot_price = prices.get(spot_ticker)
            if spot_price is not None and float(spot_price) > 0:
                return float(spot_price)
        except Exception as e:
            logger.warning(f"Web3: failed to fetch {spot_ticker} for USD conversion: {e}")

        return 0.0

    async def get_budget_snapshot(self) -> Dict[str, Any]:
        """Returns spendable Web3 budget in USD for venue-level sizing."""
        if not self.account:
            return {"status": "error", "message": "Web3 account not configured.", "available_usd": 0.0}

        if not self.enabled:
            return {"status": "error", "message": "Web3 is not enabled.", "available_usd": 0.0}

        try:
            base_units = await self.get_account_cash()
            price_usd = await self.get_base_token_price_usd()
            balance_usd = float(base_units) * float(price_usd)
            return {
                "status": "success",
                "base_symbol": settings.WEB3_BASE_TOKEN_SYMBOL,
                "base_units": float(base_units),
                "price_usd": float(price_usd),
                "balance_usd": float(balance_usd),
                # Kept explicit for monitor sizing logic parity with T212 spendable cash semantics.
                "available_usd": float(balance_usd),
                "source": "web3_balance_x_price",
            }
        except Exception as e:
            logger.error(f"Web3 budget snapshot failed: {e}")
            return {"status": "error", "message": str(e), "available_usd": 0.0}

web3_service = Web3BrokerageService()
