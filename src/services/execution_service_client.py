import grpc
import logging
import time
import inspect
from decimal import Decimal
from typing import List, Optional
from src.generated import execution_pb2
from src.generated import execution_pb2_grpc
from src.services.latency_interceptor import LatencyClientInterceptor
from src.config import settings

logger = logging.getLogger(__name__)

# Hard deadline for all RPC calls (feature 033).
# Exceeding this triggers immediate cancellation and fallback logic.
# Bug M-11: Increased from 50ms to 500ms to avoid premature timeouts.
_RPC_DEADLINE_SECONDS = 0.500
_ATTEMPT_TTL_SECONDS = 3600

def _to_decimal_str(value) -> str:
    """Serialise a numeric value to an exact decimal string, avoiding float repr."""
    return str(Decimal(str(value)))

class ExecutionServiceClient:
    def __init__(self, host: str = None, port: int = None):
        self.host = host or settings.EXECUTION_ENGINE_HOST
        self.port = port or settings.EXECUTION_ENGINE_PORT
        self.channel_url = f"{self.host}:{self.port}"
        self.interceptor = LatencyClientInterceptor()
        self._channel = None
        self._stub = None

    async def get_stub(self):
        if self._stub is None:
            self._channel = grpc.aio.insecure_channel(
                self.channel_url,
                interceptors=[self.interceptor]
            )
            self._stub = execution_pb2_grpc.ExecutionServiceStub(self._channel)
        return self._stub

    async def execute_trade(
        self,
        signal_id: str,
        pair_id: str,
        legs: List[dict],
        max_slippage: Optional[float] = None,
        risk_multiplier: Optional[float] = None,
    ) -> Optional[execution_pb2.ExecutionResponse]:
        """
        Sends an ExecutionRequest to the Java engine.

        All price/quantity/slippage fields are transmitted as exact decimal
        strings (feature 033) to prevent IEEE-754 precision loss across the
        gRPC boundary. The call is subject to a 500ms deadline.
        """
        from src.services.redis_service import redis_service
        from src.services.risk_service import risk_service
        client_order_id = f"order-{signal_id}"
        attempt_key = f"execution_attempt:{signal_id}"

        async def _load_attempt() -> dict:
            loaded = await redis_service.get_json(attempt_key)
            if isinstance(loaded, dict):
                return loaded
            return {}

        async def _save_attempt(state: str, note: str = "", **extra):
            attempt = {
                "signal_id": signal_id,
                "client_order_id": client_order_id,
                "state": state,
                "updated_at_ns": time.time_ns(),
                "note": note,
            }
            attempt.update(extra)
            await redis_service.set_json(attempt_key, attempt, ex=_ATTEMPT_TTL_SECONDS)
            logger.info("Idempotency transition signal=%s -> %s (%s)", signal_id, state, note)

        attempt = await _load_attempt()
        current_state = attempt.get("state")

        if current_state in {"ACCEPTED", "LOCKED_IN_FLIGHT"}:
            status = await self.get_trade_status(signal_id)
            if status is not None:
                await _save_attempt("ACCEPTED", "reconciled existing execution", last_status=int(status.status))
                return status
            await _save_attempt("UNKNOWN_REQUIRES_RECONCILIATION", "status probe inconclusive")
            return execution_pb2.ExecutionResponse(
                signal_id=signal_id,
                status=execution_pb2.STATUS_BROKER_ERROR,
                message="Unknown broker state; reconciliation required before retry",
            )

        if current_state == "UNKNOWN_REQUIRES_RECONCILIATION":
            status = await self.get_trade_status(signal_id)
            if status is not None:
                await _save_attempt("ACCEPTED", "reconciled unknown state", last_status=int(status.status))
                return status
            await _save_attempt("FAILED_BEFORE_SUBMIT", "reconciliation found no order")

        try:
            if max_slippage is None or risk_multiplier is None:
                ref_ticker = legs[0]["ticker"] if legs else "GENERIC"
                params = risk_service.get_execution_params(ref_ticker)
                if inspect.isawaitable(params):
                    params = await params
                if max_slippage is None:
                    max_slippage = params["max_slippage_pct"]
                if risk_multiplier is None:
                    risk_multiplier = params["risk_multiplier"]
                logger.info(
                    "RiskService: dynamic params for %s — slippage=%s mult=%s",
                    signal_id, max_slippage, risk_multiplier,
                )

            execution_legs = [
                execution_pb2.ExecutionRequest.ExecutionLeg(
                    ticker=leg["ticker"],
                    side=(
                        execution_pb2.SIDE_BUY
                        if leg["side"].upper() == "BUY"
                        else execution_pb2.SIDE_SELL
                    ),
                    quantity=_to_decimal_str(leg["quantity"]),
                    target_price=_to_decimal_str(leg["target_price"]),
                )
                for leg in legs
            ]

            await _save_attempt("LOCKED_IN_FLIGHT", "dispatching request")
            
            request = execution_pb2.ExecutionRequest(
                signal_id=signal_id,
                pair_id=pair_id,
                timestamp_ns=time.time_ns(),
                max_slippage_pct=_to_decimal_str(max_slippage),
                risk_multiplier=_to_decimal_str(risk_multiplier),
                legs=execution_legs,
                client_order_id=client_order_id,
            )
            logger.debug("gRPC: client_order_id=%s for signal=%s", client_order_id, signal_id)

            logger.info("gRPC: Sending ExecutionRequest %s to %s", signal_id, self.channel_url)
            stub = await self.get_stub()
            response = await stub.ExecuteTrade(request, timeout=_RPC_DEADLINE_SECONDS)
            if response is None:
                await _save_attempt("UNKNOWN_REQUIRES_RECONCILIATION", "server returned None after dispatch")
                return None
            if response.status == execution_pb2.STATUS_SUCCESS:
                await _save_attempt("ACCEPTED", "broker accepted")
            else:
                await _save_attempt("REJECTED_RETRYABLE", "broker rejected", last_status=int(response.status), message=response.message)
            return response

        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                logger.error(
                    "gRPC DEADLINE_EXCEEDED for %s — %.0f ms budget exhausted, cancelling.",
                    signal_id,
                    _RPC_DEADLINE_SECONDS * 1000,
                )
                await _save_attempt("UNKNOWN_REQUIRES_RECONCILIATION", "deadline exceeded after dispatch")
            else:
                logger.error(
                    "gRPC error executing trade %s: %s — %s", signal_id, e.code(), e.details()
                )
                await _save_attempt("UNKNOWN_REQUIRES_RECONCILIATION", f"grpc error after dispatch: {e.code()}")
            return None
        except Exception as e:
            logger.error("Unexpected error in ExecutionServiceClient.execute_trade: %s", e)
            await _save_attempt("FAILED_BEFORE_SUBMIT", f"client exception before dispatch: {e}")
            return None

    async def get_trade_status(
        self, signal_id: str
    ) -> Optional[execution_pb2.ExecutionResponse]:
        try:
            stub = await self.get_stub()
            return await stub.GetTradeStatus(
                execution_pb2.TradeStatusRequest(signal_id=signal_id),
                timeout=_RPC_DEADLINE_SECONDS,
            )
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                logger.error("gRPC DEADLINE_EXCEEDED on GetTradeStatus for %s.", signal_id)
            else:
                logger.error("gRPC error on GetTradeStatus %s: %s", signal_id, e.code())
            return None

    async def trigger_kill_switch(
        self, reason: str, liquidate: bool = True
    ) -> Optional[execution_pb2.KillSwitchResponse]:
        try:
            stub = await self.get_stub()
            return await stub.TriggerKillSwitch(
                execution_pb2.KillSwitchRequest(reason=reason, liquidate=liquidate),
                timeout=_RPC_DEADLINE_SECONDS,
            )
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                logger.error("gRPC DEADLINE_EXCEEDED on TriggerKillSwitch.")
            else:
                logger.error("gRPC error on TriggerKillSwitch: %s — %s", e.code(), e.details())
            return None
        except Exception as e:
            logger.error("Unexpected error in ExecutionServiceClient.trigger_kill_switch: %s", e)
            return None

    async def close(self):
        if self._channel:
            await self._channel.close()


execution_client = ExecutionServiceClient()
