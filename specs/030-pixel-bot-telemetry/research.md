# Research: Agent Thought Journal Dashboard with Pixel Bot

**Feature Branch**: `030-pixel-bot-telemetry` | **Date**: 2026-04-06

## Decisions & Rationale

### 1. Decoupled Backend Telemetry Pattern
- **Decision**: Use an `asyncio.Queue` with a single consumer background task for broadcasting.
- **Rationale**: Direct WebSocket writes from the trading loop would introduce blocking IO latency. By pushing to a queue (`put_nowait`), the hot path returns in < 1ms.
- **Alternatives considered**: Synchronous `requests` (too slow), Redis Pub/Sub (overkill for internal dashboard).

### 2. Frontend Ring-Buffer Implementation
- **Decision**: Use a standard React state array with `slice(-100)` logic.
- **Rationale**: Managing 100 DOM nodes is trivial for modern browsers. Complex virtualized lists (like `react-window`) add unnecessary bundle weight for this scale.
- **Alternatives considered**: `react-window` (rejected: too complex for 100 items), vanilla JS DOM injection (rejected: bypasses React state sync).

### 3. Pixel Bot Mood Mapping
- **Decision**: Establish a priority-based mood resolution in `App.tsx`.
- **Logic**:
  1. `HIGH_VOLATILITY` -> `GLITCH` (Red Aura)
  2. `ACHIEVABILITY < 0.9` OR `KALMAN_ERROR` -> `DOUBT` (Yellow Aura)
  3. `SHARPE > 1.5` AND `ACTIVE_SIGNALS > 0` -> `HAPPY` (Green/Blue Aura)
  4. Default -> `IDLE` (Dim Aura)
- **Rationale**: Immediate visual feedback on the highest-priority risk regime.

### 4. GPU-Accelerated CSS
- **Decision**: Force Layer Promotion via `will-change: transform` and `translate3d(0,0,0)`.
- **Rationale**: Prevents layout thrashing during high-frequency sprite frame swaps. Offloads rendering to the GPU, leaving the main thread free for telemetry parsing.

## Best Practices

### FastAPI WebSockets
- Use `ConnectionManager` to handle `WebSocketDisconnect` gracefully.
- Send JSON strings directly to avoid unnecessary middle-man object conversions in the broadcast loop.

### React Performance
- Wrap `PixelBot` and `ThoughtJournal` in `React.memo` to prevent re-renders unless their specific telemetry data changes.
- Use `useEffect` with WebSocket event listeners to manage the connection lifecycle.
