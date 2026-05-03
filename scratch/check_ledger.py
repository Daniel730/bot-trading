import asyncio
import uuid
from src.services.persistence_service import persistence_service, TradeLedger, OrderStatus
from sqlalchemy import select

async def check_ledger():
    async with persistence_service.AsyncSessionLocal() as session:
        stmt = select(TradeLedger)
        result = await session.execute(stmt)
        trades = result.scalars().all()
        
        print(f"Total trades in ledger: {len(trades)}")
        for t in trades:
            print(f"ID: {t.id} | Signal: {t.signal_id} | Ticker: {t.ticker} | Venue: {t.venue} | Status: {t.status.value} | PnL: {t.metadata_json.get('pnl') if t.metadata_json else 'N/A'}")

if __name__ == "__main__":
    asyncio.run(check_ledger())
