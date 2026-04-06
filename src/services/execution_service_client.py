import grpc
import logging
import time
from typing import List, Optional
from src.generated import execution_pb2
from src.generated import execution_pb2_grpc
from src.services.latency_interceptor import LatencyClientInterceptor
from src.config import settings

logger = logging.getLogger(__name__)

class ExecutionServiceClient:
    def __init__(self, host: str = None, port: int = None):
        self.host = host or settings.EXECUTION_ENGINE_HOST
        self.port = port or settings.EXECUTION_ENGINE_PORT
        self.channel_url = f"{self.host}:{self.port}"
        
        # Initialize interceptor
        self.interceptor = LatencyClientInterceptor()
        
        # Create channel and intercept it
        self._channel = None
        self._stub = None

    async def get_stub(self):
        if self._stub is None:
            # Use async channel
            self._channel = grpc.aio.insecure_channel(
                self.channel_url,
                interceptors=[self.interceptor]
            )
            self._stub = execution_pb2_grpc.ExecutionServiceStub(self._channel)
        return self._stub

    async def execute_trade(self, signal_id: str, pair_id: str, legs: List[dict], 
                     max_slippage: float = 0.001, risk_multiplier: float = 1.0) -> Optional[execution_pb2.ExecutionResponse]:
        """
        Sends an ExecutionRequest to the Java Engine.
        """
        try:
            execution_legs = []
            for leg in legs:
                execution_legs.append(execution_pb2.ExecutionRequest.ExecutionLeg(
                    ticker=leg['ticker'],
                    side=execution_pb2.SIDE_BUY if leg['side'].upper() == "BUY" else execution_pb2.SIDE_SELL,
                    quantity=leg['quantity'],
                    target_price=leg['target_price']
                ))

            request = execution_pb2.ExecutionRequest(
                signal_id=signal_id,
                pair_id=pair_id,
                timestamp_ns=time.time_ns(),
                max_slippage_pct=max_slippage,
                risk_multiplier=risk_multiplier,
                legs=execution_legs
            )

            logger.info(f"gRPC: Sending ExecutionRequest {signal_id} to {self.channel_url}")
            stub = await self.get_stub()
            response = await stub.ExecuteTrade(request)
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC Error executing trade {signal_id}: {e.code()} - {e.details()}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in gRPC ExecutionServiceClient: {e}")
            return None

    async def get_trade_status(self, signal_id: str) -> Optional[execution_pb2.ExecutionResponse]:
        """
        Queries the status of a previous signal.
        """
        try:
            request = execution_pb2.TradeStatusRequest(signal_id=signal_id)
            stub = await self.get_stub()
            return await stub.GetTradeStatus(request)
        except grpc.RpcError as e:
            logger.error(f"gRPC Error getting status for {signal_id}: {e.code()} - {e.details()}")
            return None

    async def close(self):
        if self._channel:
            await self._channel.close()

execution_client = ExecutionServiceClient()
