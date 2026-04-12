# Data Model: Agent Thought Journal Dashboard with Pixel Bot

**Feature Branch**: `030-pixel-bot-telemetry` | **Date**: 2026-04-06

## Entities

### TelemetryMessage (JSON)
The primary packet streamed via WebSocket.

| Field | Type | Description |
| :--- | :--- | :--- |
| `type` | String | Enum: `risk`, `thought`, `bot_state` |
| `timestamp` | DateTime | ISO-8601 UTC timestamp |
| `data` | Object | Payload corresponding to the type |

### RiskMetrics (Payload)
Broad-casted every few seconds or upon regime change.

| Field | Type | Description |
| :--- | :--- | :--- |
| `risk_multiplier` | Float | Current position scaling (0.0 to 1.0) |
| `max_drawdown_pct` | Float | Cumulative portfolio drawdown |
| `volatility_status`| Enum | `NORMAL`, `HIGH_VOLATILITY` |
| `l2_entropy` | Float | Shannon Entropy of market depth |

### AgentThought (Payload)
Streamed as agents reach sub-conclusions.

| Field | Type | Description |
| :--- | :--- | :--- |
| `agent_name` | String | `ORCHESTRATOR`, `BULL`, `BEAR`, `SEC` |
| `signal_id` | UUID | Correlation ID for the arbitrage leg |
| `thought` | String | Semantic reasoning text |
| `verdict` | Enum | `BULLISH`, `BEARISH`, `NEUTRAL`, `VETO` |

## State Management (Frontend)

### LogBuffer
- **Collection**: `List<AgentThought>`
- **Max Length**: 100
- **Policy**: FIFO (First-In, First-Out)

### MoodState
- **ActiveMood**: `IDLE` | `DOUBT` | `GLITCH` | `HAPPY`
- **Derivation**: Derived from most recent `RiskMetrics` and `AgentThought` verdicts.
