import asyncio
from src.services.persistence_service import persistence_service, TradeLedger, OrderStatus
from sqlalchemy import select

async def count_open():
    async with persistence_service.AsyncSessionLocal() as session:
        stmt = select(TradeLedger).where(TradeLedger.status == OrderStatus.OPEN)
        result = await session.execute(stmt)
        open_trades = result.scalars().all()
        print(f"Open trades: {len(open_trades)}")
        
        # Also print signal IDs for open trades
        signals = set(str(t.signal_id) for t in open_trades)
        print(f"Open signals: {len(signals)}")
        for s in signals:
            print(f"  - {s}")

if __name__ == "__main__":
    asyncio.run(count_open())
