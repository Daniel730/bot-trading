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
7. `PAPER_TRADING=true` routes to `shadow_service`; live mode routes through `BrokerageService` to Trading 212 or Web3 depending on ticker venue.

## Runtime State

| Store | Used For |
|---|---|
| Redis | Kalman state, latest prices, telemetry, L2 books, fundamental scores, idempotency helpers |
| PostgreSQL | Trade ledger, agent reasoning, journal, market regime, audit tables |
| SQLite (`data/trading_bot.db` by default) | Runtime state, budgets, config audit, local fallback |
| `data/pairs.json` | Dashboard-edited pair universe override |
| `data/bot_settings.json` | Dashboard-edited setting override |

## Modes

| Setting | Backend behavior |
|---|---|
| `PAPER_TRADING=true` | Simulated fills through shadow service, no live broker submissions |
| `DEV_MODE=true` | Crypto-only test universe, 24/7 market-hours bypass, development behavior |
| `LIVE_CAPITAL_DANGER=true` | Requires Redis entropy baselines for configured pairs before startup |
| `REGION=US/EU` | Selects hedge/compliance path in risk services |

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
