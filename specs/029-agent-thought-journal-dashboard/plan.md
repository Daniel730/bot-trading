# Implementation Plan: Agent Thought Journal Dashboard

**Branch**: `029-agent-thought-journal-dashboard` | **Date**: 2026-04-06 | **Spec**: [specs/029-agent-thought-journal-dashboard/spec.md]
**Input**: Feature specification from `/specs/029-agent-thought-journal-dashboard/spec.md`

## Summary

The Agent Thought Journal Dashboard implements a real-time observability layer that streams critical risk metrics and agent reasoning from the Python Orchestrator to the frontend. This version introduces the **Pixel Bot**, a high-density visual state indicator, and enforces strict frontend performance constraints (ring-buffer, hardware acceleration) to ensure command center stability during market volatility.

## Technical Context

**Language/Version**: Python 3.11, TypeScript (React), JavaScript (Vanilla fallback)  
**Primary Dependencies**: FastAPI (WebSockets), React (Framer Motion, Sprite Animator), asyncio  
**Design Pattern**: Asynchronous Producer-Consumer, Ring-Buffer (Frontend)  
**Target Platform**: Linux (Docker)  
**Performance Goals**: < 100ms telemetry latency; 0ms execution impact; memory-stable frontend  
**Constraints**: Bounded DOM elements (100 logs); Hardware-accelerated CSS animations  

## Project Structure

### Source Code

```text
src/
├── services/
│   ├── dashboard_service.py (Update: WebSocket endpoint, ConnectionManager)
│   └── telemetry_service.py (Update: Async Queue, Fire-and-forget broadcast)

frontend/
├── src/
│   ├── components/
│   │   ├── PixelBot.tsx (Update: Mood mapping, Hardware acceleration)
│   │   └── ThoughtJournal.tsx (New: Ring-buffer implementation)
│   ├── services/
│   │   └── api.ts (Update: WebSocket client integration)
│   └── App.tsx (Update: Integrate Risk HUD and PixelBot state)
```

## Strategy

1.  **Backend Telemetry**:
    *   Enhance `TelemetryService` with an `asyncio.Queue` (size 1000).
    *   Implement a background consumer that broadcasts to `DashboardService.connection_manager`.
    *   Add hooks to `RiskService` and `Orchestrator` to push metrics and thoughts.

2.  **Frontend WebSocket (React)**:
    *   Update `frontend/src/services/api.ts` to support WebSocket connections to `/ws/telemetry`.
    *   Implement a React hook `useTelemetry` to handle incoming messages and state updates.

3.  **Pixel Bot Integration**:
    *   Map `volatility_status == "HIGH_VOLATILITY"` to `GLITCH`.
    *   Map `sharpe > 1.5` and active signals to `HAPPY`.
    *   Map Kalman Filter confidence or L2 achievability < 0.9 to `DOUBT`.
    *   Default to `IDLE`.
    *   Ensure `PixelBot.tsx` uses `will-change: transform` and `translate3d` for performance.

4.  **Thought Journal Ring-Buffer**:
    *   Implement a specialized component that maintains a maximum of 100 entries in the DOM.
    *   Use React state optimization to prevent full-list re-renders on every tick.

5.  **Performance & Memory Audit**:
    *   Verify zero GIL blocking in Python.
    *   Profile browser memory usage under 1000+ msg/sec simulation.
