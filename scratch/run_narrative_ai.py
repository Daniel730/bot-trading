import asyncio
import sys
import os

# Ensure src is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.agents.portfolio_manager_agent import portfolio_manager_agent
from src.agents.macro_economic_agent import macro_economic_agent
from src.services.persistence_service import persistence_service

async def run_narrative_ai():
    print("!!! INICIANDO SCAN NARRATIVO: INTELIGÊNCIA ARTIFICIAL (Setor Leader: NVDA) !!!")
    
    # 1. Update beacon regime
    # Note: MacroEconomicAgent will fetch real data via DataService
    print("\n[H1] Verificando Regime do Farol (NVIDIA)...")
    regime = await macro_economic_agent.get_ticker_regime("NVDA")
    print(f"Resultado: NVDA está em regime {regime}")
    
    # 2. Run Narrative Scan
    print(f"\n[H2] Iniciando Scan de Followers no setor 'Information Technology'...")
    result = await portfolio_manager_agent.run_narrative_scan('Information Technology', 'NVDA')
    
    if result["status"] == "VETOED":
        print(f"SCAN VETADO: {result['reason']}")
    else:
        print("SCAN CONCLUÍDO COM SUCESSO. Verificando candidatos na DB...")
        # (Fetching from DB logic here if needed)

if __name__ == "__main__":
    asyncio.run(run_narrative_ai())
