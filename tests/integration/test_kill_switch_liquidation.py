import pytest
import asyncio
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.execution_service_client import execution_client
from src.generated import execution_pb2

@pytest.mark.asyncio
async def test_kill_switch_trigger_and_rejection():
    """
    T017: Verify that triggering the Kill Switch through the client
    works and subsequent trades are rejected (simulated).
    """
    reason = "Flash Crash Simulated"
    
    with patch.object(execution_client, 'get_stub', new_callable=AsyncMock) as mock_get_stub:
        mock_stub = MagicMock()
        
        # 1. Mock TriggerKillSwitch response
        mock_stub.TriggerKillSwitch = AsyncMock(return_value=execution_pb2.KillSwitchResponse(
            success=True,
            status_message="System Halted",
            orders_cancelled=5,
            positions_liquidated=2
        ))
        mock_get_stub.return_value = mock_stub
        
        # Trigger it
        response = await execution_client.trigger_kill_switch(reason, liquidate=True)
        
        assert response.success is True
        assert response.orders_cancelled == 5
        assert response.positions_liquidated == 2
        
        # 2. Mock ExecuteTrade to return STATUS_HALTED
        mock_stub.ExecuteTrade = AsyncMock(return_value=execution_pb2.ExecutionResponse(
            signal_id="123",
            status=execution_pb2.STATUS_HALTED,
            message="Engine Halted"
        ))
        
        # Mock Redis and Risk service dependencies
        with patch('src.services.execution_service_client.settings'), \
             patch('src.services.redis_service.redis_service') as mock_redis, \
             patch('src.services.risk_service.risk_service') as mock_risk:
             
            mock_redis.set_nx = AsyncMock(return_value=True)
            mock_risk.get_execution_params = AsyncMock(return_value={
                "max_slippage_pct": 0.01,
                "risk_multiplier": 1.0
            })
            
            trade_resp = await execution_client.execute_trade(
                str(uuid.uuid4()), "KO_PEP", 
                [{"ticker": "KO", "side": "BUY", "quantity": 1, "target_price": 1.0}]
            )
            
            assert trade_resp.status == execution_pb2.STATUS_HALTED
            assert "Halted" in trade_resp.message

@pytest.mark.asyncio
async def test_kill_switch_error_handling():
    """
    Verify client handles gRPC errors during kill switch trigger.
    """
    with patch.object(execution_client, 'get_stub', new_callable=AsyncMock) as mock_get_stub:
        mock_stub = MagicMock()
        # Simulate gRPC error
        mock_stub.TriggerKillSwitch = AsyncMock(side_effect=Exception("gRPC Connection Lost"))
        mock_get_stub.return_value = mock_stub
        
        response = await execution_client.trigger_kill_switch("test")
        assert response is None
