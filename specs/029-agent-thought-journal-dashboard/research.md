# Research: Agent Thought Journal Dashboard

**Feature Branch**: `029-agent-thought-journal-dashboard` | **Date**: 2026-04-06

## Current State Analysis

### Telemetry Implementation
- **File**: `src/services/telemetry_service.py`
- **Current State**: Primarily a stub for syncing outcomes to an external central server (POST requests).
- **Gaps**: No real-time streaming capability or local dashboard broadcast mechanism.

### Dashboard Streaming
- **File**: `src/services/dashboard_service.py`
- **Current State**: Uses Server-Sent Events (SSE) via `EventSourceResponse` in FastAPI to push metrics and terminal messages.
- **Gaps**: SSE is uni-directional and might be less efficient for high-frequency "fire-and-forget" telemetry compared to WebSockets for this specific real-time requirement.

### Agent Logging
- **File**: `src/services/agent_log_service.py`
- **Current State**: Uses `PersistenceManager` (SQLite) to log thoughts synchronously (via `print` and DB writes).
- **Gaps**: No connection between agent reasoning generation and the real-time dashboard stream.

## Proposed Technical Solutions

### Asynchronous Telemetry Manager
Instead of each agent calling the dashboard directly, we will implement a centralized `TelemetryManager` within `TelemetryService` that uses an `asyncio.Queue`. 
- Producers (Agents, RiskService) push to the queue.
- A background consumer task drains the queue and broadcasts via WebSockets.
- This ensures zero latency impact on the producer's execution path.

### WebSocket over SSE
While SSE works for the current dashboard, WebSockets provide a more robust full-duplex channel for interactive telemetry and lower overhead for frequent, small JSON updates (thoughts, risk ticks).

### Risk Parameter Hooks
We will add hooks in `RiskService.get_execution_params` to automatically push the calculated `risk_multiplier`, `max_drawdown`, and `volatility_status` to the `TelemetryService`.

## Performance Benchmarks (Estimated)
- **JSON Serialization**: < 1ms for small updates.
- **Queue Push**: < 0.1ms (atomic `put_nowait`).
- **End-to-end Latency**: ~20-50ms (network-dependent).
- **Execution Path Overhead**: Near zero due to fire-and-forget.
