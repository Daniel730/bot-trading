import pytest
import asyncio
from datetime import datetime, timedelta
from src.services.risk_service import RiskService

@pytest.fixture
def risk_svc():
    return RiskService()

def test_sector_freeze_logic(risk_svc):
    sector = "Technology"
    assert not risk_svc.is_sector_frozen(sector)
    
    risk_svc.trigger_sector_freeze(sector, "Test rationale")
    assert risk_svc.is_sector_frozen(sector)
    
    # Manually expire the freeze
    risk_svc.sector_freezes[sector] = datetime.now() - timedelta(seconds=1)
    assert not risk_svc.is_sector_frozen(sector)

def test_multiple_sector_freezes(risk_svc):
    risk_svc.trigger_sector_freeze("Tech", "R1")
    risk_svc.trigger_sector_freeze("Finance", "R2")
    
    assert risk_svc.is_sector_frozen("Tech")
    assert risk_svc.is_sector_frozen("Finance")
    assert not risk_svc.is_sector_frozen("Energy")
