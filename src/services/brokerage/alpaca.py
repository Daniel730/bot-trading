import asyncio
import logging
import alpaca_trade_api as tradeapi
from typing import List, Dict, Any, Optional
from src.config import settings
from src.services.brokerage.base import AbstractBrokerageProvider

logger = logging.getLogger(__name__)

class AlpacaProvider(AbstractBrokerageProvider):
    def __init__(self, api_key: str = None, api_secret: str = None, base_url: str = None):
        self.api_key = api_key or settings.ALPACA_API_KEY.strip()
        self.api_secret = api_secret or settings.ALPACA_API_SECRET.strip()
        self.base_url = base_url or settings.ALPACA_BASE_URL.strip()
        
        self.api = tradeapi.REST(
            self.api_key,
            self.api_secret,
            self.base_url,
            api_version='v2'
        )

    def test_connection(self) -> bool:
        try:
            self.api.get_account()
            return True
        except Exception as e:
            logger.error(f"Alpaca connection failed: {e}")
            return False

    async def place_market_order(self, ticker: str, quantity: float, side: str, limit_price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        try:
            order_type = 'limit' if limit_price else 'market'
            params = {
                'symbol': ticker,
                'qty': quantity,
                'side': side.lower(),
                'type': order_type,
                'time_in_force': 'day'
            }
            if limit_price:
                params['limit_price'] = limit_price
            if client_order_id:
                params['client_order_id'] = client_order_id

            order = await asyncio.to_thread(self.api.submit_order, **params)
            return {
                "status": "success",
                "order_id": order.id,
                "broker": "ALPACA",
                "client_order_id": order.client_order_id
            }
        except Exception as e:
            logger.error(f"Alpaca order failed for {ticker}: {e}")
            return {"status": "error", "message": str(e)}

    async def place_value_order(self, ticker: str, amount: float, side: str, price: float = None, client_order_id: str = None) -> Dict[str, Any]:
        try:
            # Alpaca supports notional orders (value-based) natively for many assets
            params = {
                'symbol': ticker,
                'notional': amount,
                'side': side.lower(),
                'type': 'market',
                'time_in_force': 'day'
            }
            if client_order_id:
                params['client_order_id'] = client_order_id

            order = await asyncio.to_thread(self.api.submit_order, **params)
            return {
                "status": "success",
                "order_id": order.id,
                "broker": "ALPACA",
                "client_order_id": order.client_order_id
            }
        except Exception as e:
            logger.warning(f"Alpaca notional order failed for {ticker}, falling back to quantity: {e}")
            # Fallback to calculating quantity if notional is not supported for this asset
            from src.services.data_service import data_service
            if price is None:
                prices = await data_service.get_latest_price_async([ticker])
                price = prices.get(ticker)
            
            if not price or price <= 0:
                return {"status": "error", "message": f"Invalid price for {ticker} fallback"}
            
            quantity = amount / price
            return await self.place_market_order(ticker, quantity, side, client_order_id=client_order_id)

    def get_portfolio(self) -> List[Dict[str, Any]]:
        try:
            positions = self.api.list_positions()
            return [self._normalize_position(p) for p in positions]
        except Exception as e:
            logger.error(f"Alpaca failed to fetch portfolio: {e}")
            return []

    def get_positions(self, ticker: str = None) -> List[Dict[str, Any]]:
        try:
            if ticker:
                try:
                    p = self.api.get_position(ticker)
                    return [self._normalize_position(p)]
                except:
                    return []
            positions = self.api.list_positions()
            return [self._normalize_position(p) for p in positions]
        except Exception as e:
            logger.error(f"Alpaca failed to fetch positions: {e}")
            return []

    def get_account_cash(self) -> float:
        try:
            account = self.api.get_account()
            return float(account.cash)
        except Exception as e:
            logger.error(f"Alpaca failed to fetch account cash: {e}")
            return 0.0

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        try:
            orders = self.api.list_orders(status='open')
            return [self._normalize_order(o) for o in orders]
        except Exception as e:
            logger.error(f"Alpaca failed to fetch pending orders: {e}")
            return []

    def get_symbol_metadata(self, ticker: str) -> Dict[str, Any]:
        try:
            asset = self.api.get_asset(ticker)
            return {
                "ticker": asset.symbol,
                "minTradeQuantity": 0.0001 if asset.fractionable else 1.0,
                "quantityIncrement": 0.0001 if asset.fractionable else 1.0,
                "tickSize": 0.01,
                "status": asset.status
            }
        except Exception as e:
            logger.error(f"Alpaca failed to fetch metadata for {ticker}: {e}")
            return {}

    def _normalize_position(self, p) -> Dict[str, Any]:
        return {
            "ticker": p.symbol,
            "quantity": float(p.qty),
            "quantityAvailableForTrading": float(p.qty_available) if hasattr(p, 'qty_available') else float(p.qty),
            "averagePrice": float(p.avg_entry_price),
            "currentPrice": float(p.current_price),
            "marketValue": float(p.market_value)
        }

    def _normalize_order(self, o) -> Dict[str, Any]:
        return {
            "ticker": o.symbol,
            "quantity": float(o.qty) if o.qty else 0.0,
            "side": o.side.upper(),
            "status": o.status,
            "limitPrice": float(o.limit_price) if o.limit_price else None,
            "id": o.id
        }
