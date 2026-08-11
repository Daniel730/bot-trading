# Python Backend

`src/` contains the trading monitor, dashboard API, brokerage dispatch, risk services, agent ensemble, persistence, and telemetry glue.

## Main Entrypoints

| File | Purpose |
|---|---|
| `monitor.py` | Main arbitrage scan loop; starts dashboard API on port `8080` |
| `mcp_server.py` | Optional FastMCP SSE tool server on port `8000` |
| `daemons/sec_fundamental_worker.py` | Background SEC/EDGAR scoring worker |
| `config.py` | Pydantic settings, pair universe, runtime overrides |

## Core Flow

1. `ArbitrageMonitor.initialize_pairs()` builds the candidate universe from configured equity pairs plus crypto pairs, unless `DEV_MODE=true`.
2. `pair_eligibility_service` rejects unsupported cross-session, cross-currency, high-cost, and short-hold LSE pairs before Kalman state is allocated.
3. Historical prices warm Kalman filters and run static plus optional rolling cointegration checks.
4. Each scan computes a z-score from the prior Kalman state, persists filter state to Redis, and compares against the entry threshold.
5. High z-score signals pass through the orchestrator: macro beacon veto, bull/bear agents, Redis SEC scores, whale watcher, portfolio/risk confidence, and historical accuracy scaling.
6. Approved signals request human approval through Telegram/dashboard before execution.
7. `PAPER_TRADING=true` routes to `shadow_service`; broker-connected mode routes through `BrokerageService` to the active Alpaca broker path. Trading 212 and Web3 routes are legacy/disabled in the current runtime.

`src/monitor.py` order routing: `PAPER_TRADING=true` is the **SHADOW** lane (`shadow_service` only). `PAPER_TRADING=false` with Alpaca's paper API is **BROKER_PAPER** (real paper orders via Python `BrokerageService`). Real Alpaca URLs are **LIVE**. Ledger metadata stamps `execution_lane` / `is_shadow` with the open `signal_id`; closes follow the open lane so mode flips do not double-count or orphan fills. The Java execution engine is a dry-run/audit sidecar and is not the monitor's default order path.

## Runtime State

| Store | Used For |
|---|---|
| Redis | Kalman state (sliding TTL), latest prices, telemetry, L2 books, fundamental scores (`sec:integrity`), idempotency helpers. Dashboard sessions are JWT/in-process, not Redis. |
| PostgreSQL | Trade ledger, agent reasoning, journal, market regime, audit tables |
| SQLite (`data/trading_bot.db` by default) | Runtime state, budgets, config audit, local fallback |
| `data/pairs.json` | Dashboard-edited pair universe override |
| `data/bot_settings.json` | Dashboard-edited setting override |

## Modes

| Setting / lane | Backend behavior |
|---|---|
| `PAPER_TRADING=true` → **SHADOW** | Simulated fills through `shadow_service` only; no broker submissions. Ledger rows tagged `is_shadow` / `execution_lane=SHADOW` with the same `signal_id` as journal/reasoning. |
| `PAPER_TRADING=false` + Alpaca paper API → **BROKER_PAPER** | Real orders on Alpaca paper money via `BrokerageService`; auto-approve; never calls shadow execute. |
| Real Alpaca URL → **LIVE** | Real-money broker path; human approval required. |
| `DEV_MODE=true` | Crypto-only test universe, 24/7 market-hours bypass; not counted as `ALPACA_PAPER`. |
| `LIVE_CAPITAL_DANGER=true` | Requires Redis entropy baselines for live endpoints (skipped for `ALPACA_PAPER`). |
| `REGION=US/EU` | Selects hedge/compliance path in risk services |

Opens refuse mixing SHADOW and broker-lane open signals. Closes follow the lane stamped at open (not only the current env flag) so mode flips cannot double-submit or orphan fills. PnL is written once via `persistence.close_trade`.

## Dashboard API

`monitor.py` attaches itself to `dashboard_service` and starts Uvicorn on port `8080`. Auth model: Bearer `DASHBOARD_TOKEN` + `X-Dashboard-Session`. Login is fail-closed (Telegram approval or TOTP/backup when 2FA is enabled — no token-only session). Sensitive config/settings writes require OTP once 2FA is enabled.

Important routes (not exhaustive):

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/auth/login` | Token + Telegram challenge or OTP |
| `POST` | `/api/auth/login/complete` | Finish Telegram challenge |
| `POST` | `/api/auth/login/cancel` | Cancel pending challenge |
| `POST` | `/api/auth/logout` | End session |
| `POST` | `/api/auth/2fa/initiate` | Start TOTP setup |
| `POST` | `/api/auth/2fa/verify` | Confirm TOTP / verify codes |
| `GET` | `/stream` | SSE telemetry |
| `WS` | `/ws/telemetry` | WebSocket telemetry (auth required) |
| `GET` | `/ping` | Unauthenticated liveness |
| `GET`/`POST` | `/api/pairs` | Pair universe |
| `POST` | `/api/pairs/discover` | One-shot discovery (scout still frozen by default) |
| `GET` | `/api/stats/summary`, `/api/stats/trades`, `/api/stats/charts/{metric}` | Stats |
| `GET` | `/api/system/health`, `/api/system/logs` | Health / logs |
| `GET`/`POST` | `/api/config`, `/api/config/update` | Runtime config |
| `GET`/`POST` | `/api/settings` | Settings (OTP for sensitive writes) |
| `POST` | `/api/bot/control`, `/api/bot/restart` | Operator control |
| `GET`/`POST` | `/api/approvals/...` | Pending trade approvals |
| `GET` | `/api/positions`, `/api/broker/positions`, `/api/broker/unmanaged` | Ledger vs broker inventory |
| `POST` | `/api/wallet/sync` | Wallet sync |

All operational routes (except `/ping`) require both a valid dashboard token and a valid dashboard session.

## Telemetry

`src/services/telemetry_service.py` is an **internal** in-process queue that broadcasts to dashboard WebSocket clients. Remote `sync_outcomes()` is a no-op. Vendor tracing is opt-in via `src/services/otel_service.py` (`OTEL_ENABLED` + OTLP endpoint; #118). Errors are opt-in via `src/services/sentry_service.py` (fail-closed when `SENTRY_DSN` empty; #119).

## Tests

```bash
PYTHONPATH=. pytest tests/ -v --asyncio-mode=auto
PYTHONPATH=. pytest tests/unit -v --asyncio-mode=auto
PYTHONPATH=. pytest tests/integration -v --asyncio-mode=auto
```

Use focused tests when touching shared trading logic:

```bash
PYTHONPATH=. pytest tests/unit/test_pair_eligibility.py -v --asyncio-mode=auto
PYTHONPATH=. pytest tests/unit/test_slippage_guard.py -v --asyncio-mode=auto
PYTHONPATH=. pytest tests/integration/test_portfolio_orchestration.py -v --asyncio-mode=auto
```