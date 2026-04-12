import pytest
from src.services.calibration_service import CalibrationService, AchievabilityStatus
from datetime import datetime, timezone

@pytest.fixture
def calibration_service():
    return CalibrationService()

@pytest.mark.asyncio
async def test_perfect_fill_calibration(calibration_service):
    # Mock L2 Snapshot (Top of book)
    # Mid = (100.00 + 100.02) / 2 = 100.01
    l2_snapshot = [
        {"bid_price": 100.00, "bid_size": 1000, "ask_price": 100.02, "ask_size": 1000},
        {"bid_price": 99.98, "bid_size": 2000, "ask_price": 100.04, "ask_size": 2000}
    ]
    
    # Requested 100 shares (10% of top depth)
    # VWAP = 100.02 (top of book)
    # Impact = 0.5bps (10% depth consumed)
    # Adjusted = 100.02 * (1 + 0.5/10000) = 100.025001
    requested_qty = 100
    actual_fill = 100.025
    
    analysis = await calibration_service.run_fill_achievability_audit(
        trade_id="trade_123",
        l2_snapshot=l2_snapshot,
        requested_qty=requested_qty,
        actual_fill_price=actual_fill
    )
    
    assert analysis["achievability_status"] == AchievabilityStatus.PERFECT
    assert analysis["theoretical_mid_price"] == pytest.approx(100.01)

@pytest.mark.asyncio
async def test_unachievable_fill_too_good(calibration_service):
    l2_snapshot = [
        {"bid_price": 100.00, "bid_size": 1000, "ask_price": 100.02, "ask_size": 1000}
    ]
    
    # Actual fill is BETTER than the model (no slippage/impact)
    # Model expects 100.025, but actual is 100.01 (mid-price)
    # Difference = (100.025 - 100.01)/100.01 * 10000 = 1.49bps 
    # Wait, the status logic is:
    # diff_bps = (impact_adjusted - actual_fill) / theoretical_mid * 10000
    # if diff_bps > 2 -> UNACHIEVABLE
    
    # Let's force it: 100.04 model, 100.01 actual -> diff = 3bps
    actual_fill = 100.005 # Better than mid price!
    
    analysis = await calibration_service.run_fill_achievability_audit(
        trade_id="trade_456",
        l2_snapshot=l2_snapshot,
        requested_qty=500, # 50% depth
        actual_fill_price=actual_fill
    )
    
    assert analysis["achievability_status"] == AchievabilityStatus.UNACHIEVABLE

@pytest.mark.asyncio
async def test_insufficient_depth_rejection(calibration_service):
    l2_snapshot = [
        {"bid_price": 100.0, "bid_size": 10, "ask_price": 101.0, "ask_size": 10}
    ]
    # Requested 100 but only 10 available
    analysis = await calibration_service.run_fill_achievability_audit(
        trade_id="trade_789",
        l2_snapshot=l2_snapshot,
        requested_qty=100,
        actual_fill_price=101.0
    )
    
    assert analysis["status"] == "UNACHIEVABLE"
    assert "Insufficient liquidity" in analysis["reason"]
