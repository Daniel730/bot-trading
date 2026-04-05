# Data Model: Dashboard Terminal

## DashboardState Entities

### BotMessage
Represents a communication from the bot or the system to the user.

| Field | Type | Description |
|-------|------|-------------|
| id | String | Unique UUID for the message. |
| type | Enum | `BOT`, `SYSTEM`, `USER`. |
| text | String | Content of the message. |
| timestamp | DateTime | When the message was sent/received. |
| metadata | Object | Optional fields like `correlation_id` for approval buttons. |

### TerminalState
New properties added to the global `DashboardState`.

| Property | Type | Description |
|----------|------|-------------|
| messages | List<BotMessage> | Last 50 messages to display in the terminal. |
| is_modal_open | Boolean | UI state for the terminal modal. |

## Persistence (Existing SQLite)
No new tables are required in SQLite as the terminal state is transient (kept in memory and cleared on restart). However, interactions sent via the terminal MUST be logged to the existing `logs` table as part of the `Thought Journal` (Principle III).

## API Contracts

### POST `/api/terminal/command`
Send a command from the dashboard to the bot.

**Request Body**:
```json
{
  "command": "/approve" || "/status" || "/exposure",
  "metadata": {
    "correlation_id": "abc123" 
  }
}
```

**Response (200 OK)**:
```json
{
  "status": "received",
  "response": "Processing command..."
}
```

### SSE Stream (`/stream`)
The existing SSE payload will be extended.

**New Payload Format**:
```json
{
  "stage": "string",
  "details": "string",
  "metrics": { ... },
  "active_signals": [ ... ],
  "terminal_messages": [
    { "id": "uuid", "type": "BOT", "text": "...", "timestamp": "ISO-8601" }
  ],
  "timestamp": "ISO-8601"
}
```
