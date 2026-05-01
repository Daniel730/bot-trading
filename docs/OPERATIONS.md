# Operations Guide

This is the day-to-day guide for running the bot locally or through Docker.

## First-Time Setup

```bash
cp .env.template .env
```

Set these before starting anything:

| Variable | Why it matters |
|---|---|
| `POSTGRES_PASSWORD` | Required. The app refuses default/blank database secrets. |
| `DASHBOARD_TOKEN` | Required. Used for dashboard login, session signing, and secret protection. |
| `DASHBOARD_ALLOWED_ORIGINS` | Keep this scoped to the origins you actually use. |
| `PAPER_TRADING=true` | Recommended default while validating the stack. |
| `DRY_RUN=true` | Required for the Java engine today. |

Optional but useful:

- `POLYGON_API_KEY` for market data.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for approvals and login approval notifications.
- `T212_API_KEY`, `T212_API_SECRET`, and `TRADING_212_MODE` for Trading 212.
- `ALPACA_API_KEY`, `ALPACA_API_SECRET`, and `ALPACA_BASE_URL` for Alpaca.
- `BROKERAGE_PROVIDER=T212` or `BROKERAGE_PROVIDER=ALPACA` to choose the active equity broker.
- `WEB3_*` variables for on-chain crypto execution in live mode.
- `OPENAI_API_KEY` and/or `GEMINI_API_KEY` for model-backed analysis paths.

## Local Run

Backend:

```bash
pip install -r requirements.txt
python scripts/init_db.py
python src/monitor.py
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Java engine:

```bash
cd execution-engine
gradle shadowJar --no-daemon
DRY_RUN=true gradle run --no-daemon
```

Optional FastMCP tool server:

```bash
python src/mcp_server.py
```

## Docker Run

Production image mode:

```bash
docker compose -f infra/docker-compose.yml up -d
```

Local build mode:

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.local.yml \
  up -d --build --remove-orphans
```

Check status and logs:

```bash
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs -f bot
docker compose -f infra/docker-compose.yml logs -f execution-engine
docker compose -f infra/docker-compose.yml logs -f frontend
```

## Dashboard Login

1. Open `http://localhost:3000` in Docker or the Vite dev URL locally.
2. Enter `DASHBOARD_TOKEN`.
3. If Telegram notifications are configured, approve the login notification.
4. If TOTP is enabled, provide an authenticator or backup code when needed.

The dashboard removes old `token`/`session` query params from the URL. API auth is header-based.

## Operating Modes

| Mode | Settings | Notes |
|---|---|---|
| Paper | `PAPER_TRADING=true` | Shadow service simulates entries/exits and persists auditable rows. |
| Live broker/Web3 | `PAPER_TRADING=false` | Python brokerage dispatcher submits live orders. Confirm all secrets and approvals first. |
| Broker selection | `BROKERAGE_PROVIDER=T212` or `BROKERAGE_PROVIDER=ALPACA` | Non-crypto tickers route to the selected equity broker; `*-USD` crypto tickers can route to Web3 when live. |
| Dev | `DEV_MODE=true` | Crypto test universe, 24/7 scan, equity-hour bypass. Do not use for production decisions. |
| Java dry run | `DRY_RUN=true` | Required. The Java engine rejects live-broker mode today. |

## Daily Checks

- Confirm dashboard mode shows the expected `PAPER`, `LIVE`, or `DEV` state.
- Confirm Redis and PostgreSQL are healthy.
- Confirm the scan loop logs `SCAN [A/B]` lines.
- Confirm pair rejections are expected when eligibility filtering is enabled.
- Watch `/api/system/health` or the System Health dashboard page for CPU/memory pressure.
- In paper mode, verify `signal_id` joins across reasoning, journal, and trade ledger.
- In live mode, confirm Telegram approval, active broker connectivity, and sell-inventory preflight before enabling unattended execution.

## Telegram And Dashboard Commands

Telegram handlers include:

| Command | Purpose |
|---|---|
| `/exposure` | Sector exposure summary |
| `/invest` | Investment helper entrypoint |
| `/cash` | Account cash and sweep status |
| `/portfolio` | Portfolio view |
| `/why TICKER` | Current thesis/explanation for a ticker |
| `/macro` | Macro/regime summary |

Dashboard terminal handlers include:

| Command | Purpose |
|---|---|
| `/status` | Send current dashboard state |
| `/approve <id>` | Approve a pending dashboard/Telegram correlation id |
| `/set_threshold <amount>` | Update auto-trade approval threshold |
| `/exposure` | Dashboard exposure summary |

## Troubleshooting

| Symptom | Check |
|---|---|
| App refuses to boot | `POSTGRES_PASSWORD` and `DASHBOARD_TOKEN` must be non-default. |
| Dashboard cannot connect | Backend dashboard API must be listening on `:8080`; check CORS origins. |
| SSE reconnect loop | Confirm `/stream` is reachable and both auth headers are present. |
| WebSocket disconnects | Confirm the initial auth message includes token and session. |
| Java engine exits | Set `DRY_RUN=true`; confirm Redis/Postgres env vars. |
| Equity orders use the wrong broker | Check `BROKERAGE_PROVIDER`; valid values are `T212` and `ALPACA`. |
| No equity scans | Check market hours and `DEV_MODE`; crypto pairs run 24/7, equity pairs are gated. |
| Many pairs rejected | Review `BLOCK_CROSS_CURRENCY_PAIRS`, `BLOCK_LSE_PAIRS_FOR_SHORT_HOLD`, `PAIR_MAX_ROUND_TRIP_COST_PCT`, and `ALLOW_EU_CONTINENTAL_OVERLAP`. |
| Live sell leg rejected before broker | The preflight inventory guard found insufficient available shares. |
