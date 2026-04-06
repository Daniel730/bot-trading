import grpc
import time
import logging
from typing import Any, Callable, Coroutine
from src.services.redis_service import redis_service

logger = logging.getLogger(__name__)

class LatencyClientInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """
    gRPC Async Client Interceptor to measure nanosecond-precision RTT and 
    pass client-side timestamps to the server.
    """
    async def intercept_unary_unary(
        self,
        continuation: Callable[[grpc.aio.ClientCallDetails, Any], Coroutine[Any, Any, grpc.aio.UnaryUnaryCall]],
        client_call_details: grpc.aio.ClientCallDetails,
        request: Any,
    ) -> Any:
        # Capture sent time
        sent_ns = time.perf_counter_ns()
        
        # Add sent timestamp to metadata
        metadata = []
        if client_call_details.metadata is not None:
            metadata = list(client_call_details.metadata)
        
        metadata.append(("x-sent-ns", str(sent_ns)))
        metadata.append(("x-metric-version", "1"))
        
        # Create new details with updated metadata
        new_details = grpc.aio.ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=metadata,
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
        )
        
        try:
            # Execute the call
            call = await continuation(new_details, request)
            
            # Wait for the response
            response = await call
            
            # Capture received time
            received_ns = time.perf_counter_ns()
            
            # Calculate RTT
            rtt_ns = received_ns - sent_ns
            
            # Extract server-side metadata from trailers
            trailers = await call.trailing_metadata()
            trailers_dict = dict(trailers)
            
            received_at_server_ns = int(trailers_dict.get('x-received-ns', 0))
            processed_at_server_ns = int(trailers_dict.get('x-processed-ns', 0))
            
            # Metric versioning check
            server_version = trailers_dict.get('x-metric-version', '0')
            if server_version != "1":
                logger.warning(f"gRPC Metric Version mismatch: Client=1, Server={server_version}")

            # Push metrics to Redis
            signal_id = getattr(request, 'signal_id', 'unknown')
            latency_metrics = {
                "signal_id": signal_id,
                "client_sent_ns": sent_ns,
                "client_received_ns": received_ns,
                "server_received_ns": received_at_server_ns,
                "server_processed_ns": processed_at_server_ns,
                "rtt_ns": rtt_ns,
                "status": "OK"
            }
            
            logger.info(f"gRPC Latency [{signal_id}]: RTT={rtt_ns/1_000_000:.3f}ms")
            await redis_service.push_latency_metrics(latency_metrics)
            
            return response

        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                signal_id = getattr(request, 'signal_id', 'unknown')
                logger.error(f"gRPC DEADLINE_EXCEEDED for {signal_id}. Triggering LATENCY_ALARM.")
                # We record a failed latency metric
                latency_metrics = {
                    "signal_id": signal_id,
                    "client_sent_ns": sent_ns,
                    "client_received_ns": time.perf_counter_ns(),
                    "status": "DEADLINE_EXCEEDED"
                }
                await redis_service.push_latency_metrics(latency_metrics)
            raise e
