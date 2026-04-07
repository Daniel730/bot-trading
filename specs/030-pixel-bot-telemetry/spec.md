# Feature Specification: Agent Thought Journal Dashboard with Pixel Bot

**Feature Branch**: `030-pixel-bot-telemetry`  
**Created**: 2026-04-06  
**Status**: Draft  
**Input**: User description: "feature="029-agent-thought-journal-dashboard" context="frontend/src/components/PixelBot.tsx,frontend/src/App.tsx,dashboard/index.html,dashboard/app.js,src/services/dashboard_service.py,src/services/telemetry_service.py" requirements="1. Architect an asynchronous WebSocket telemetry stream from the Python Orchestrator to the React/vanilla frontend. 2. Implement the 'Pixel Bot' UI element that dynamically updates its sprite/expression (idle, doubt, glitch, happy) based on the agent's Thought Journal and Risk States. 3. Visually expose the active Risk Multiplier, Current Drawdown %, and Volatility Status (L2 Shannon Entropy level). 4. The frontend must use a strict ring-buffer (max 100 entries) for the Thought Journal logs to prevent DOM bloat and memory leaks. 5. The backend telemetry service must use a decoupled fire-and-forget pattern to guarantee zero latency impact on the core arbitrage execution hot path.""

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Institutional HUD & Risk HUD (Priority: P1)

As a fund manager, I want to see the real-time risk parameters (Risk Multiplier, Drawdown %, Volatility Status) on the dashboard, so I can understand the current risk exposure and regime at a glance.

**Why this priority**: Essential for situational awareness during high-volatility events where manual intervention may be required.

**Independent Test**: Can be tested by simulating backend risk updates and verifying the values update correctly on the HUD without page refresh.

**Acceptance Scenarios**:

1. **Given** the system is in HIGH_VOLATILITY status, **When** the dashboard receives a risk update, **Then** the "VOL_STATE" indicator must change to "HIGH_VOLATILITY" and Entropy level must update.
2. **Given** a portfolio drawdown of 10%, **When** the risk update is pushed, **Then** the "RISK_MULT" value must reflect the current scaling factor (e.g., 0.33).

---

### User Story 2 - Pixel Bot Emotional State (Priority: P1)

As a quant developer, I want the system's "Mood" to be visually represented by a Pixel Bot sprite, so I can intuitively sense system health without reading logs.

**Why this priority**: Reduces cognitive load by providing a high-density visual summary of complex agent states.

**Independent Test**: Can be tested by broadcasting different "bot_state" events and verifying the Pixel Bot changes its sprite/expression accordingly.

**Acceptance Scenarios**:

1. **Given** a Volatility Switch trigger, **When** the glitch state is received, **Then** the Pixel Bot expression must switch to "GLITCH".
2. **Given** optimal execution (High Sharpe, active trades), **When** the happy state is received, **Then** the Pixel Bot must appear "HAPPY/AGGRESSIVE".
3. **Given** low fill achievability or Kalman mismatch, **When** the doubt state is received, **Then** the Pixel Bot must appear "DOUBTFUL".

---

### User Story 3 - Stable Thought Journal (Priority: P2)

As a systems operator, I want to see the live reasoning of all agents in a scrolling journal that remains stable over long periods, so I can audit decisions without the dashboard crashing.

**Why this priority**: Critical for long-term monitoring stability and auditing AI behavior in real-time.

**Independent Test**: Can be tested by streaming 1000+ messages and verifying that the DOM contains no more than 100 log entries.

**Acceptance Scenarios**:

1. **Given** 150 consecutive agent thoughts, **When** the journal updates, **Then** only the most recent 100 entries must be present in the dashboard UI.

---

### User Story 4 - Zero-Latency Telemetry (Priority: P1)

As an architect, I want the telemetry system to have zero impact on the execution speed of the trading bot, so that observability does not cost us "alpha".

**Why this priority**: Execution speed is the primary competitive advantage; observability must be secondary.

**Independent Test**: Verified via integration tests measuring gRPC execution time with and without telemetry active.

**Acceptance Scenarios**:

1. **Given** active telemetry broadcasting, **When** a trade is executed, **Then** the hot path latency must not increase beyond the 1.5ms budget.

### Edge Cases

- **WebSocket Disconnection**: If the browser client disconnects, the backend must continue processing without blocking on queue overflow.
- **Message Bursts**: During a flash crash, the system may generate thousands of updates; the frontend must throttle rendering to stay responsive.
- **Unauthorized Access**: WebSocket connections must be rejected if an invalid token is provided.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST implement a dedicated real-time telemetry channel for low-latency dashboard updates.
- **FR-002**: Telemetry broadcasting MUST be decoupled from the trading execution loop to ensure zero impact on order latency.
- **FR-003**: System MUST stream real-time risk metrics (`risk`, `thought`, and `bot_state` events).
- **FR-004**: Frontend MUST implement a strict memory-safe buffer (max 100 entries) for the log stream.
- **FR-005**: Pixel Bot component MUST visually reflect 4 distinct system regimes: `IDLE`, `DOUBT`, `GLITCH`, and `HAPPY`.
- **FR-006**: Frontend animations and log transitions MUST be hardware-accelerated to maintain UI responsiveness.
- **FR-007**: Telemetry updates MUST follow a "fire-and-forget" pattern where execution continues immediately after the update is queued.

### Key Entities *(include if feature involves data)*

- **TelemetryUpdate**: A JSON record containing a type, timestamp, and data payload (risk metrics or agent thoughts).
- **PixelBotMood**: An enumerated state representing the visual expression of the bot.
- **LogEntry**: A single reasoning record from an agent, capped by the ring-buffer.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Dashboard UI remains responsive (60fps) during bursts of 100+ updates per second.
- **SC-002**: Zero (0ms) measurable increase in core arbitrage execution latency due to telemetry.
- **SC-003**: Frontend memory footprint remains stable (< 300MB) over a 24-hour monitoring session.
- **SC-004**: 100% of critical risk triggers (Volatility Switch, Stop Loss) are reflected on the dashboard in < 100ms.

## Assumptions

- **Browser Capabilities**: Users are using modern browsers with hardware acceleration and WebSocket support.
- **Network Bandwidth**: The local/internal network can handle the telemetry stream bandwidth.
- **Asset Availability**: The `bot_spritesheet.png` contains the necessary frames for the 4 mood states.
