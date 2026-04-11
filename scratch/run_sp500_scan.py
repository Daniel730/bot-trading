import asyncio
import sys
import os

# Ensure src is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.services.persistence_service import persistence_service, UniverseCandidate
from src.agents.portfolio_manager_agent import portfolio_manager_agent
from sqlalchemy import select

async def run_scan():
    print("!!! INICIANDO SCAN DO UNIVERSO S&P 500 (SETOR FINANCEIRO) !!!")
    
    # 1. Init DB schema
    await persistence_service.init_db()
    
    # 2. Run scan for a sector (Financials involves high correlation usually)
    # The scan_sector_universe method we wrote limits pairs for performance
    await portfolio_manager_agent.scan_sector_universe('Financials')
    
    # 3. Fetch results
    print("\n--- RESULTADOS DO SCAN (CANDIDATOS ENCONTRADOS) ---")
    async with persistence_service.AsyncSessionLocal() as session:
        stmt = select(UniverseCandidate).order_by(UniverseCandidate.sortino.desc())
        result = await session.execute(stmt)
        candidates = result.scalars().all()
        
        if not candidates:
            print("Nenhum par cointegrado encontrado neste scan parcial.")
        else:
            for c in candidates:
                print(f"Par: {c.pair_id} | Setor: {c.sector}")
                print(f"  > P-Value: {c.p_value:.4f} (Cointegrado!)")
                print(f"  > Correlation: {c.correlation:.3f}")
                print(f"  > Sortino Projetado: {c.sortino:.2f}")
                print(f"  > Retorno Esperado: {c.expected_return*100:.2f}% p.a.\n")

if __name__ == "__main__":
    asyncio.run(run_scan())
