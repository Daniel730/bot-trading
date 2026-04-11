from typing import Dict, List
from src.services.persistence_service import persistence_service, OrderSide, OrderStatus
from src.config import settings
import uuid

class ShadowService:
    def __init__(self):
        pass

    async def execute_simulated_trade(self, pair_id: str, direction: str, size_a: float, size_b: float, price_a: float, price_b: float):
        """
        Records a simulated trade in the Virtual Ledger (PostgreSQL).
        """
        t_a, t_b = pair_id.split('_')
        
        trade_id_a = str(uuid.uuid4())
        trade_id_b = str(uuid.uuid4())
        signal_id = uuid.uuid4()

        # Log Leg A
        await persistence_service.log_trade({
            "order_id": trade_id_a,
            "signal_id": signal_id,
            "ticker": t_a,
            "side": OrderSide.SELL if direction == "Short-Long" else OrderSide.BUY,
            "quantity": size_a,
            "price": price_a,
            "status": OrderStatus.OPEN,
            "metadata": {"is_shadow": True, "direction": direction}
        })

        # Log Leg B
        await persistence_service.log_trade({
            "order_id": trade_id_b,
            "signal_id": signal_id,
            "ticker": t_b,
            "side": OrderSide.BUY if direction == "Short-Long" else OrderSide.SELL,
            "quantity": size_b,
            "price": price_b,
            "status": OrderStatus.OPEN,
            "metadata": {"is_shadow": True, "direction": direction}
        })

        print(f"SHADOW TRADE EXECUTED: {direction} for {pair_id} at {price_a}/{price_b}")
        return signal_id

    async def close_simulated_trade(self, pair_id: str, signal_id: uuid.UUID, direction: str, size_a: float, size_b: float, entry_price_a: float, entry_price_b: float, exit_price_a: float, exit_price_b: float):
        """
        Closes a simulated trade and calculates PnL.
        """
        if direction == "Short-Long":
            pnl_a = (entry_price_a - exit_price_a) * size_a
            pnl_b = (exit_price_b - entry_price_b) * size_b
        else: # "Long-Short"
            pnl_a = (exit_price_a - entry_price_a) * size_a
            pnl_b = (entry_price_b - exit_price_b) * size_b
            
        total_pnl = pnl_a + pnl_b
        
        exit_prices = {
            "exit_price_a": exit_price_a,
            "exit_price_b": exit_price_b
        }
        await persistence_service.close_trade(signal_id, exit_prices, total_pnl)
        
        print(f"SHADOW TRADE CLOSED: {direction} for {pair_id} (PnL: {total_pnl:.2f})")
        return total_pnl

    async def get_active_portfolio_with_sectors(self) -> List[Dict]:
        """
        Retrieves active shadow positions and maps them to their sectors.
        """
        from sqlalchemy import select
        from src.services.persistence_service import TradeLedger
        
        async with persistence_service.AsyncSessionLocal() as session:
            stmt = select(TradeLedger).where(TradeLedger.status == OrderStatus.OPEN)
            result = await session.execute(stmt)
            trades = result.scalars().all()
            
            portfolio = []
            # Map sectors by searching in PAIR_SECTORS
            for trade in trades:
                sector = "General"
                # Search pair_sectors based on ticker 
                for pair_key, pair_sector in settings.PAIR_SECTORS.items():
                    tickers_in_pair = pair_key.split('_')
                    if trade.ticker in tickers_in_pair:
                        sector = pair_sector
                        break
                        
                portfolio.append({
                    "ticker": trade.ticker,
                    "size": float(trade.quantity * trade.price), # Cast to float
                    "sector": sector 
                })
            return portfolio

shadow_service = ShadowService()
