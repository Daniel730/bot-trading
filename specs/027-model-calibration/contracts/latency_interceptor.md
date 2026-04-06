# gRPC Interceptor Contract: Model Calibration

This document defines the high-precision latency measurement contract across Python and Java services.

## Java Side (Server Interceptor)

The Java Execution Engine MUST implement a `ServerInterceptor` that captures the precise arrival and completion time of every execution request.

- **Class**: `LatencyInterceptor`
- **Hook**: `interceptCall`
- **Logic**:
  - `startNs = System.nanoTime()`
  - `onMessage(request)` -> Store `startNs` in context.
  - `onHalfClose()` -> `receivedNs = System.nanoTime()`
  - `close()` -> `processedNs = System.nanoTime()`
  - Send these timestamps back to Python via gRPC metadata headers (trailers) or a dedicated telemetry log.

## Python Side (Client Interceptor)

The Python Orchestrator MUST implement a `UnaryUnaryClientInterceptor` to wrap all outgoing execution requests.

- **Class**: `LatencyClientInterceptor`
- **Hook**: `intercept_unary_unary`
- **Logic**:
  - `sentNs = time.perf_counter_ns()`
  - `call = continuation(client_call_details, request)`
  - `receivedNs = time.perf_counter_ns()`
  - Calculate `RTT = receivedNs - sentNs`.
  - Push metrics to Redis for real-time monitoring.

## Common Metadata Headers

Metadata keys for timestamp exchange (optional, if using header-based RTT calculation):
- `x-sent-ns`: Python Client Sent Time.
- `x-received-ns`: Java Server Received Time.
- `x-processed-ns`: Java Server Processed Time.
