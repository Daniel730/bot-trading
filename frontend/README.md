# Alpha Arbitrage Frontend

React 19 + TypeScript operations console for the trading bot. The first screen is the authenticated console used to inspect runtime state, pair eligibility, positions, signals, approvals, configuration, and system health.

## Stack

- React 19
- Vite 8 (dev proxy: `/api`, `/stream` → `http://localhost:8080`; `/ws` → `ws://localhost:8080`)
- TypeScript 5
- lucide-react icons
- framer-motion (partial: e.g. `PairsPanel`, `IntelligenceHub` — broader motion tracked in #134)
- ESLint 9 (`npm run lint`) + Biome 2 (`npm run lint:biome` / `format` / `check`) — coexistence: ESLint remains the CI lint gate; Biome is warn-first until a dedicated format PR
- Vitest + Testing Library
- nginx static serving in Docker

## Local Development

```bash
npm install --legacy-peer-deps
npm run dev
```

Install must use `--legacy-peer-deps` (matches CI): `react-sprite-animator` declares a React 17 peer while the app is React 19.

Vite serves the app on `http://localhost:5173` unless another port is selected. The Vite proxy forwards `/api`, `/stream`, and `/ws` to the dashboard on `8080`, so same-origin relative fetches work in dev without CORS. When the app decides an absolute API base URL (localhost and not port `8080`), it still targets `http://localhost:8080`. Remote nginx deployments use the same origin so `/api`, `/stream`, and `/ws` are handled by nginx proxy rules.

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
npm run lint         # ESLint 9 (CI gate)
npm run lint:biome   # Biome lint
npm run format       # Biome format --write
npm run format:check # Biome format check
npm run check        # Biome check (lint+format; CI warn-first)
npm run knip         # Dead code/deps scan (CI warn-first; cleanup in a follow-up PR)
npm run test         # Vitest
npm run preview      # preview built bundle
```

### Knip notes

`frontend/knip.json` treats Vite entrypoints + Vitest specs as entries. CI runs `npm run knip` warn-first; the first cleanup of unused exports/deps should be a separate PR after the baseline is reviewed. `@vitest/coverage-v8` is intentionally ignored (CI installs it ad hoc).

### Lint/format decision (ESLint + Biome)

Keep **ESLint** as the authoritative React/hooks gate (`npm run lint`). Use **Biome** for fast format/lint feedback locally and as a non-blocking CI signal (`continue-on-error`). Avoid enabling overlapping style rules that fight ESLint; migrate formatting-only responsibility to Biome in a later incremental PR (no mass rewrite here).

## Authentication Flow

1. The user enters `DASHBOARD_TOKEN`.
2. Login **fails closed**: without a valid token (and Telegram approval **or** OTP when 2FA is enabled), no dashboard session is created. There is no token-only session.
3. Prefer Telegram login approval when available; use authenticator/backup OTP when Telegram is offline or 2FA is required. If Telegram is unavailable and 2FA is not yet enabled, bootstrap 2FA (see `AGENTS.md`) before logging in.
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
