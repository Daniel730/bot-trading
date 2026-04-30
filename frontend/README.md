# Alpha Arbitrage Frontend

The frontend is a React 19 + TypeScript operations console for the trading bot. It is not a marketing site: the first screen is the authenticated console used to inspect runtime state, pair eligibility, positions, trade history, bot controls, configuration, and system health.

## Stack

- React 19
- Vite 8
- TypeScript 5
- lucide-react icons
- Vitest + Testing Library
- nginx static serving in Docker

## Local Development

```bash
npm install
npm run dev
```

Vite serves the app on `http://localhost:5173` unless another port is selected. When the app runs on localhost and not on port `8080`, API calls are sent to `http://localhost:8080`.

Optional environment variables:

```bash
VITE_API_URL=http://localhost:8080
VITE_API_TIMEOUT_MS=15000
```

## Commands

```bash
npm run dev      # Vite dev server
npm run build    # TypeScript build + Vite bundle
npm run lint     # ESLint
npm run test     # Vitest
npm run preview  # preview built bundle
```

## Authentication Flow

1. The user enters `DASHBOARD_TOKEN`.
2. The backend creates a dashboard session after notification approval, or falls back to token-only when notifications are unavailable and 2FA is not enabled.
3. API requests send `Authorization: Bearer <dashboard-token>` and `X-Dashboard-Session: <session-token>`.
4. SSE uses the same headers against `/stream`.
5. WebSocket telemetry connects to `/ws/telemetry` and sends an initial auth message with the dashboard token and session.

Sensitive dashboard config writes require TOTP or a backup code once 2FA is enabled.

## Main Screens

| Screen | Purpose |
|---|---|
| Overview | Balance, uptime, P&L, positions, risk telemetry, agent reasoning |
| Pairs | Active/configured pairs, cointegration status, hot reload, T212 wallet seeding |
| Analytics | Profit and win/loss chart summaries |
| Trade History | Search and filter executed trade groups |
| Bot Control | Start/stop/restart requests and terminal feed |
| Settings | Editable runtime settings, masked secrets, 2FA-gated sensitive changes |
| System Health | CPU, memory, network, logs, and event feed |

## Docker

The Dockerfile builds the static bundle with Node 20 and serves it with `nginx:alpine`:

```bash
docker build -t trading-frontend .
docker run --rm -p 3000:80 trading-frontend
```

The nginx config proxies `/api/`, `/stream`, and `/ws/` to the backend service.
