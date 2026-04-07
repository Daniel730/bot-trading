# Research: Agent Thought Journal Dashboard

**Feature Branch**: `029-agent-thought-journal-dashboard` | **Date**: 2026-04-06

## Current State Analysis

### Frontend Dual-Path
The project currently has two frontends:
1.  **Vanilla (`/dashboard`)**: Uses SSE and simple DOM manipulation.
2.  **React (`/frontend`)**: Uses Vite and Framer Motion.
- **Decision**: Feature 029 will prioritize the React frontend for institucional use, keeping the vanilla dashboard as a fallback.

### Sprite Animation (Pixel Bot)
- **Library**: `react-sprite-animator` is already present in `frontend/src/components/PixelBot.tsx`.
- **Performance**: Standard React state updates for every WebSocket tick can cause re-renders. We will use `React.memo` and scoped state to isolate the Pixel Bot and Log list.

### DOM Performance (Ring-Buffer)
- **Problem**: Long-running dashboards accumulate thousands of `<div>` nodes, leading to "layout thrashing" and high memory usage.
- **Solution**: A strict ring-buffer (FIFO) implementation in React. When the list length exceeds 100, the oldest entry is dropped from state.

## Proposed Technical Solutions

### Asynchronous Telemetry Manager
- Producers (Agents, RiskService) push to `asyncio.Queue`.
- Consumer task broadcasts via WebSockets.
- Ensures zero latency impact on the producer's execution path.

### Pixel Bot Mood Mapping
| Regime | Logic | Pixel Bot Expression |
| :--- | :--- | :--- |
| **Volatile** | `volatility_status == HIGH` | `GLITCH` |
| **Uncertain** | `fill_achievability < 90%` OR `kalman_mismatch` | `DOUBT` |
| **Optimal** | `sharpe > 1.5` AND `active_trades` | `HAPPY/AGGRESSIVE` |
| **Normal** | Default | `IDLE` |

### CSS Hardware Acceleration
To prevent browser freezing during high-frequency updates, we will enforce:
- `will-change: transform, opacity` on all dynamic elements.
- `transform: translate3d(0,0,0)` to force GPU composition.
- Throttled UI updates (max 60fps) for the log stream.
