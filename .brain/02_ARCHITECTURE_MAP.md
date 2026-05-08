# Architecture Map

## Topology

```text
React dashboard
  -> Python dashboard API on port 8080
  -> Python monitor loop
       -> Redis for fast state
       -> PostgreSQL for ledger/audit state
       -> SQLite for local runtime/config state
       -> Alpaca brokerage facade for current live equity path
       -> shadow service for paper execution
       -> Java gRPC execution engine on port 50051 when used
FastMCP server on port 8000 is a separate optional assistant/tool surface.
```

## Primary Components

| Component | Path | Current Role |
|---|---|---|
| Monitor | `src/monitor.py` | Startup, pair initialization, scan loop, z-score signals, approval, live/paper execution, exits |
| Dashboard API | `src/services/dashboard_service.py` | FastAPI operator API, sessions, SSE/WebSocket telemetry, config, wallet sync |
| Brokerage facade | `src/services/brokerage_service.py` | Current code initializes Alpaca only and exposes normalized order/account methods |
| Alpaca provider | `src/services/brokerage/alpaca.py` | Alpaca REST adapter, order submission, positions, pending orders, order snapshots |
| Persistence service | `src/services/persistence_service.py` | SQLAlchemy async PostgreSQL models and trade/journal/system-state methods |
| Local persistence | `src/models/persistence.py` | SQLite helper for legacy/local runtime tables such as CIK, events, dashboard auth state |
| Pair eligibility | `src/services/pair_eligibility_service.py` | Rejects unsupported pairs before Kalman allocation |
| Arbitrage service | `src/services/arbitrage_service.py` | Cointegration, Kalman filter state, spread/z-score math |
| Orchestrator | `src/agents/orchestrator.py` | Agent/risk validation of candidate signals |
| Risk service | `src/services/risk_service.py` | Kelly sizing and exposure/risk validation |
| Java engine | `execution-engine/` | gRPC execution/audit sidecar, dry-run only |
| Frontend | `frontend/` | React 19 + Vite dashboard |
| Infra | `infra/` | Dockerfiles, Compose, redeploy helper, systemd template |

## Persistence Boundaries

| Store | Current Use |
|---|---|
| Redis | Kalman state, latest prices, L2 books, telemetry, fundamental scores, Java idempotency helpers |
| PostgreSQL | `trade_ledger`, trade journal, agent reasoning, market regime, fill analysis |
| SQLite | dashboard auth/config state, CIK mapping, local events/logs, DCA helpers, fallback runtime state |
| `data/pairs.json` | dashboard-edited pair universe override |
| `data/bot_settings.json` | dashboard-edited settings override |

## Execution State Model

Important `OrderStatus` values in `src/services/persistence_service.py`:

- `ORDER_SUBMITTED`
- `LEG_A_FILLED`
- `LEG_A_PARTIAL`
- `LEG_A_REJECTED`
- `LEG_B_FILLED`
- `LEG_B_PARTIAL`
- `LEG_B_REJECTED`
- `OPEN_PAIR`
- `PARTIAL_EXPOSURE`
- `CLOSING`
- `CLOSE_FAILED`
- `NEEDS_MANUAL_RECONCILIATION`
- `FAILED_REQUIRES_MANUAL_RECONCILIATION`

The active safety work is moving the bot away from optimistic `OPEN`/`COMPLETED` assumptions and toward explicit unresolved states when broker reality is unknown.

## Current Architecture Divergences To Remember

- Docs still present the bot as Trading 212 / Alpaca / Web3 capable. Current `BrokerageService` forces Alpaca and logs that legacy providers moved to `legacy/`.
- `src/config.py` validates `BROKERAGE_PROVIDER`, then later sets `settings.BROKERAGE_PROVIDER = "ALPACA"`.
- The Java execution engine intentionally refuses `DRY_RUN=false`; live Java brokerage is not available.
- `infra/docker-compose.backend.yml` currently has a dirty change that introduces a fallback PostgreSQL password. This conflicts with the documented non-default-secret requirement and should be treated as a P0 security regression until resolved.

## External Interfaces

| Interface | Notes |
|---|---|
| Dashboard HTTP | Authenticated with `Authorization: Bearer <token>` plus `X-Dashboard-Session` |
| Dashboard SSE | `/stream`, same auth expectation |
| Dashboard WebSocket | `/ws/telemetry`, query/session auth or initial auth message |
| FastMCP | Optional SSE server, separate from dashboard API |
| Alpaca REST | Current live brokerage adapter |
| Telegram | Approvals, login notifications, operator alerts |
| Java gRPC | `ExecuteTrade`, `GetTradeStatus`, `TriggerKillSwitch` |

## Startup Ports

| Service | Port |
|---|---|
| Frontend dev | 5173 |
| Frontend Docker | 3000 |
| Python dashboard/API | 8080 |
| FastMCP | 8000 |
| Java execution engine | 50051 |
| Redis | 6379 |
| PostgreSQL host mapping | 5433 |
