from typing import Dict, List
from src.models.persistence import PersistenceManager
from src.config import settings

class ShadowService:
    def __init__(self):
        self.persistence = PersistenceManager(settings.DB_PATH)

    async def execute_simulated_trade(self, pair_id: str, direction: str, size_a: float, size_b: float, price_a: float, price_b: float):
        """
        Records a simulated trade in the Virtual Ledger.
        """
        trade_id = self.persistence.save_trade(pair_id, direction, size_a, size_b, price_a, price_b, is_shadow=True)
        print(f"SHADOW TRADE EXECUTED: {direction} for {pair_id} at {price_a}/{price_b} (Size: {size_a}/{size_b})")
        return trade_id

    async def close_simulated_trade(self, pair_id: str, trade_id: str, direction: str, size_a: float, size_b: float, entry_price_a: float, entry_price_b: float, exit_price_a: float, exit_price_b: float):
        """
        Closes a simulated trade and calculates PnL.
        """
        # "Short-Long" means Short A, Long B
        # "Long-Short" means Long A, Short B
        if direction == "Short-Long":
            # Profit from Short A: (entry - exit) * size
            pnl_a = (entry_price_a - exit_price_a) * size_a
            # Profit from Long B: (exit - entry) * size
            pnl_b = (exit_price_b - entry_price_b) * size_b
        else: # "Long-Short"
            pnl_a = (exit_price_a - entry_price_a) * size_a
            pnl_b = (entry_price_b - exit_price_b) * size_b
            
        total_pnl = pnl_a + pnl_b
        
        self.persistence.close_trade(trade_id, exit_price_a, exit_price_b, total_pnl)
        print(f"SHADOW TRADE CLOSED: {direction} for {pair_id} at {exit_price_a}/{exit_price_b} (PnL: {total_pnl:.2f})")
        return total_pnl

    def get_active_portfolio_with_sectors(self) -> List[Dict]:
        """
        Retrieves active shadow positions and maps them to their sectors.
        """
        # 1. Query 'Open' shadow trades from persistence
        # We assume size is the sum of size_a and size_b for simplicity in exposure check
        with self.persistence._get_connection() as conn:
            query = """
                SELECT tr.pair_id, tr.size_a, tr.size_b, ap.ticker_a, ap.ticker_b
                FROM trade_records tr
                JOIN arbitrage_pairs ap ON tr.pair_id = ap.id
                WHERE tr.status = 'Open' AND tr.is_shadow = 1
            """
            rows = conn.execute(query).fetchall()
            
            portfolio = []
            for row in rows:
                pair_key = f"{row['ticker_a']}_{row['ticker_b']}"
                sector = settings.PAIR_SECTORS.get(pair_key, "Unknown")
                portfolio.append({
                    "pair_id": row['pair_id'],
                    "size": row['size_a'] + row['size_b'],
                    "sector": sector
                })
            return portfolio

    def get_active_portfolio_sectors(self) -> List[str]:
        """Helper to get only the list of active sectors."""
        portfolio = self.get_active_portfolio_with_sectors()
        return list(set(trade['sector'] for trade in portfolio))

shadow_service = ShadowService()
