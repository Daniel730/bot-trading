# Quickstart: Agent Thought Journal Dashboard

**Feature Branch**: `029-agent-thought-journal-dashboard` | **Date**: 2026-04-06

## Backend Setup

1.  **WebSocket Support**:
    The `DashboardService` will be updated to include a WebSocket endpoint at `/ws/telemetry`.
    
    Ensure `uvicorn` and `fastapi` are updated to support WebSockets.

2.  **Telemetry Streaming**:
    The `TelemetryService` will start an asynchronous background task to broadcast updates from its internal queue. No manual initialization is required.

## Frontend Setup

1.  **Dashboard Access**:
    Navigate to `http://localhost:8080/?token=arbi-elite-2026`.

2.  **Real-time HUD**:
    A new HUD panel will appear on the left, displaying:
    - `RISK_MULT`: Current position scaler.
    - `DRAWDOWN`: Real-time portfolio drawdown.
    - `ENTROPY`: L2 market entropy.

3.  **Thought Stream**:
    The existing `Thought Journal` (bottom-left) will now stream live reasoning from:
    - `ORCHESTRATOR`
    - `BULL_AGENT`
    - `BEAR_AGENT`
    - `SEC_AGENT`

## Simulation/Testing

To simulate a telemetry update, you can use the following snippet in the Python REPL:

```python
import asyncio
from src.services.telemetry_service import telemetry_service

async def test_telemetry():
    await telemetry_service.broadcast({
        "type": "thought",
        "data": {
            "agent_name": "TestAgent",
            "thought": "This is a simulated thought broadcast.",
            "verdict": "INFO"
        }
    })

asyncio.run(test_telemetry())
```
