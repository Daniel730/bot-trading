# gRPC Interceptor Contract: Model Calibration

## Java Side (Server Interceptor)
- **Class**: `LatencyInterceptor`
- **Hook**: `interceptCall`
- **Logic**:
  - `startNs = System.nanoTime()`
  - `onHalfClose()` -> `x-received-ns = startNs`
  - `close()` -> `x-processed-ns = System.nanoTime()`
  - **Metadata Propagation**: Send back `x-received-ns` and `x-processed-ns` as gRPC **Trailers** (after message body).

## Python Side (Client Interceptor)
- **Class**: `LatencyClientInterceptor`
- **Hook**: `intercept_unary_unary`
- **Logic**:
  - `sentNs = time.perf_counter_ns()`
  - Send `x-sent-ns = sentNs` in **Headers**.
  - `receivedNs = time.perf_counter_ns()`
  - De-serialize Trailers: `x-received-ns`, `x-processed-ns`.
- **Error Handling**: 
  - If gRPC status is `DEADLINE_EXCEEDED`, log `latency_rtt_ns` as `null` and trigger immediate `LATENCY_ALARM`.

## Data Types & Precision
- All timestamps MUST be `int64` representing nanoseconds.
- Python: `int` (64-bit by default in Python 3).
- Java: `long`.

## Versioning
- Both sides MUST include a `x-metric-version: 1` header. Mismatched versions must result in a `WARNING` log but allow trade processing.
