# Data Model: Resolve Production Rigor Gaps

## Entities

### SystemState (Persistence)

Represents the global operational status and failure metrics of the bot.

| Field | Type | Description |
|-------|------|-------------|
| key | TEXT | Primary key (e.g., 'operational_status', 'consecutive_api_timeouts') |
| value | TEXT | Serialized value (e.g., 'NORMAL', '3') |

## State Transitions

### Operational Status

- **NORMAL**: Default state. All functions active.
- **DEGRADED_MODE**: Triggered by 3 consecutive API timeouts. New entries blocked.
- **Transition NORMAL -> DEGRADED_MODE**: Occurs in `Orchestrator.ainvoke` when timeout count reaches 3.
- **Transition DEGRADED_MODE -> NORMAL**: Requires manual reset or successful completion of a full evaluation loop (to be determined during implementation).

## Validation Rules

- **Friction Reject**: If `amount < 5.00` AND `friction_pct > 0.015`, status MUST be `FRICTION_REJECT`.
- **Hedge Mapping**: `SPY` must strictly map to `XSPS.L` in EU region.
