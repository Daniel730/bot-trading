# Alpha Arbitrage Frontend

React 19 + TypeScript operations console for the trading bot. The first screen is the authenticated console used to inspect runtime state, pair eligibility, positions, signals, approvals, configuration, and system health.

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

Vite serves the app on `http://localhost:5173` unless another port is selected. When the app runs on localhost and not on port `8080`, API calls are sent to `http://localhost:8080`. Remote nginx deployments use the same origin so `/api`, `/stream`, and `/ws` are handled by nginx proxy rules.

Deep links use hash routes such as `#/settings`, `#/wallet`, `#/control`.

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
2. Login **fails closed**: without a valid token (and approval / OTP when required), no dashboard session is created.
3. Prefer Telegram login approval when available; use authenticator/backup OTP when Telegram is offline or 2FA is required.
4. Pending Telegram approvals can be cancelled from the login screen.
5. API requests send `Authorization: Bearer <dashboard-token>` and `X-Dashboard-Session: <session-token>`.
6. SSE uses the same headers against `/stream`.
7. WebSocket telemetry connects to `/ws/telemetry` and sends an initial auth message with the dashboard token and session.

Sensitive dashboard config writes require TOTP or a backup code once 2FA is enabled. Settings Security shows a QR code, manual secret, and downloadable backup codes during setup.

## Main Screens

| Screen | Purpose |
|---|---|
| Overview | Status strip, open positions, risk telemetry, recent agent reasoning |
| Analytics | Cumulative profit and win/loss charts (single chart source of truth) |
| Trade History | Search and filter executed trade groups |
| Wallet | Broker/wallet cash and inventory sync |
| Pairs | Active/configured pairs, cointegration status, hot reload |
| Signals | Live open signals |
| Positions | Strategy and broker position panels |
| Bot Control | Start/stop/restart, pending trade approvals, live terminal commands |
| Settings | Runtime config, masked secrets, 2FA setup |
| System Health | CPU/memory history and structured health events |

## Docker

```bash
docker build -t trading-frontend .
docker run --rm -p 3000:80 trading-frontend
```

The nginx config proxies `/api/`, `/stream`, and `/ws/` to the backend service.
