# Quickstart: Agent Thought Journal Dashboard with Pixel Bot

**Feature Branch**: `030-pixel-bot-telemetry` | **Date**: 2026-04-06

## Backend Setup

1. **Verify Dependencies**:
   Ensure `fastapi` and `uvicorn` are available.
   
2. **Start the Telemetry Loop**:
   The `TelemetryService` starts automatically with the `DashboardService`.
   
3. **Trigger a Test Thought**:
   Use the following script to simulate an agent thought:
   ```python
   import asyncio
   from src.services.telemetry_service import telemetry_service
   
   async def simulate():
       telemetry_service.broadcast("thought", {
           "agent_name": "BULL",
           "thought": "Momentum confirmed above VWAP.",
           "verdict": "BULLISH"
       })
   
   asyncio.run(simulate())
   ```

## Frontend Setup

1. **Start Vite**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

2. **Access Dashboard**:
   Navigate to `http://localhost:5173/?token=arbi-elite-2026`.

3. **Verify Pixel Bot**:
   Check if the bot expression changes when sending test telemetry.

## Verification Checklist

- [ ] WebSocket handshake successful (Status: ONLINE).
- [ ] Risk HUD updates reflect simulated metrics.
- [ ] Thought Journal caps at 100 entries (no scroll performance drop).
- [ ] Pixel Bot transitions smoothly between moods.
- [ ] Core execution latency remains < 1.5ms.
