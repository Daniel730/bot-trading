
import asyncio
from src.services.persistence_service import persistence_service, TradingPair
from sqlalchemy import delete

async def clear_problematic_tickers():
    async with persistence_service.engine.begin() as conn:
        # Delete from TradingPair
        result = await conn.execute(
            delete(TradingPair).where(
                (TradingPair.ticker_a.in_(['MATIC-USD', 'POL-USD'])) | 
                (TradingPair.ticker_b.in_(['MATIC-USD', 'POL-USD']))
            )
        )
        print(f"Cleared {result.rowcount} problematic pairs from TradingPair table.")

if __name__ == "__main__":
    asyncio.run(clear_problematic_tickers())
