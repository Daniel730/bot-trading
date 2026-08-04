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

`monitor.py` attaches itself to `dashboard_service` and starts Uvicorn on port `8080`. Important routes:

- `POST /api/auth/login`
- `GET /stream`
- `WS /ws/telemetry`
- `GET/POST /api/pairs`
- `GET /api/stats/summary`
- `GET /api/stats/trades`
- `GET /api/system/health`
- `GET /api/config`
- `POST /api/config/update`

All operational routes require both a valid dashboard token and a valid dashboard session. Sensitive config writes require TOTP/backup-code verification once 2FA is enabled.

## Tests

```bash
pytest tests/ -v --asyncio-mode=auto
pytest tests/unit -v --asyncio-mode=auto
pytest tests/integration -v --asyncio-mode=auto
```

Use focused tests when touching shared trading logic:

```bash
pytest tests/unit/test_pair_eligibility.py -v --asyncio-mode=auto
pytest tests/unit/test_slippage_guard.py -v --asyncio-mode=auto
pytest tests/integration/test_portfolio_orchestration.py -v --asyncio-mode=auto
```
