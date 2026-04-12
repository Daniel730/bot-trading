# Data Model: Audit Bug Fixes & System Hardening

This document describes the data-related changes for the audit bug fixes.

## 1. Settings (src/config.py)

The `Settings` model (pydantic) is updated to remove insecure defaults.

| Field | Old Default | New Default | Rationale |
|-------|-------------|-------------|-----------|
| `POSTGRES_PASSWORD` | `"bot_pass"` | `Field(...)` (Required) | Prevent silent security regression if env var is unset. |
| `DASHBOARD_TOKEN` | `"arbi-elite-2026"` | `Field(...)` (Required) | Prevent unauthenticated access with default token. |

## 2. DashboardState (src/services/dashboard_service.py)

The `DashboardState` class is updated to manage connection limits.

- **active_connections**: `List[WebSocket]` -> Now bounded by `MAX_DASHBOARD_CONNECTIONS = 50`.
- **Logic**: New connections beyond the limit are rejected with a 403 or the oldest connection is closed (LRU).

## 3. TradingOrder (src/models/order.py or similar)

Validation logic for quantity rounding.

- **Validation**: If `quantity` is calculated from `fiat_value`, it must be checked against `MIN_TRADE_QUANTITY` (e.g., `0.000001`).
- **Action**: Raise `ValidationError` if quantity rounds to zero or falls below the minimum threshold.

## 4. Infrastructure Config

- **REGION**: New configuration field in `Settings` to specify the execution region (e.g., `"US"`, `"EU"`).
- **Docker Healthcheck**: Updated URL in `docker-compose.yml` to match the actual service health endpoint.
