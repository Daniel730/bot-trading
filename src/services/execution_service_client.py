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
                     max_slippage: Optional[float] = None, risk_multiplier: Optional[float] = None) -> Optional[execution_pb2.ExecutionResponse]:
        """
        Sends an ExecutionRequest to the Java Engine with Redis idempotency.
        Fetches dynamic risk parameters from RiskService if not provided.
        """
        # T016: Implement Redis idempotency lock
        from src.services.redis_service import redis_service
        from src.services.risk_service import risk_service
        
        lock_key = f"idempotency:{signal_id}"
        
        # SET key value NX EX 60
        is_locked = await redis_service.set_nx(lock_key, "LOCKED", expire=60)
        if not is_locked:
            logger.warning(f"Idempotency: Signal {signal_id} is already being processed. Rejecting duplicate.")
            return execution_pb2.ExecutionResponse(
                signal_id=signal_id,
                status=execution_pb2.STATUS_BROKER_ERROR,
                message="Duplicate Request - Signal already in process"
            )

        try:
            # Fetch dynamic risk parameters if not provided
            if max_slippage is None or risk_multiplier is None:
                # Use the first ticker from legs as reference for volatility
                ref_ticker = legs[0]['ticker'] if legs else "GENERIC"
                params = await risk_service.get_execution_params(ref_ticker)
                
                if max_slippage is None:
                    max_slippage = params["max_slippage_pct"]
                if risk_multiplier is None:
                    risk_multiplier = params["risk_multiplier"]
                
                logger.info(f"RiskService: Using dynamic params for {signal_id}: max_slippage={max_slippage}, risk_mult={risk_multiplier}")

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
