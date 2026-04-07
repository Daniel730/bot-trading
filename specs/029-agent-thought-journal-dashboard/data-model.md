# Data Model: Agent Thought Journal Dashboard

**Feature Branch**: `029-agent-thought-journal-dashboard` | **Date**: 2026-04-06

## Telemetry Payload Schema (JSON)

Updates will be streamed via WebSocket as JSON objects with the following types:

### 1. Risk Update (`type: "risk"`)
```json
{
  "type": "risk",
  "timestamp": "2026-04-06T12:00:00.000Z",
  "data": {
    "risk_multiplier": 0.33,
    "max_drawdown_pct": 0.10,
    "volatility_status": "HIGH_VOLATILITY",
    "l2_entropy": 0.85
  }
}
```

### 2. Agent Thought Update (`type: "thought"`)
```json
{
  "type": "thought",
  "timestamp": "2026-04-06T12:00:01.000Z",
  "data": {
    "agent_name": "BullAgent",
    "signal_id": "uuid",
    "ticker_pair": "KO_PEP",
    "thought": "Strong upward momentum detected in technical baseline.",
    "verdict": "BULLISH"
  }
}
```

### 3. System Status Update (`type: "status"`)
```json
{
  "type": "status",
  "timestamp": "2026-04-06T12:00:02.000Z",
  "data": {
    "stage": "MONITORING",
    "details": "Scanning 12 pairs for arbitrage opportunities."
  }
}
```

## Backend States

### Telemetry Queue
- **Type**: `asyncio.Queue[TelemetryUpdate]`
- **Max Size**: 1000 items (to prevent memory overflow if frontend is disconnected).

### Active Connections
- **Type**: `Set[WebSocket]`
- **Management**: Handled within `DashboardService.ConnectionManager`.
