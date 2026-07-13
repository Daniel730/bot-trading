# AGENTS.md

Project setup, code, and testing guidance live in `README.md`, `GEMINI.md`, and the per-project READMEs (`src/README.md`, `frontend/README.md`, `execution-engine/README.md`, `infra/README.md`). Read those first for standard commands.

## Cursor Cloud specific instructions

This environment is a multi-language monorepo. The update script already refreshes
Python deps (into `.venv`) and frontend deps. Everything below is non-obvious startup/run
context that is NOT handled automatically.

### Services and ports

| Service | How to run (dev) | Port |
|---|---|---|
| PostgreSQL 16 (required) | `sudo pg_ctlcluster 16 main start` | 5432 |
| Redis (required) | `sudo redis-server --daemonize yes --appendonly no` | 6379 |
| Python monitor + dashboard API (core) | `PYTHONPATH=/workspace .venv/bin/python src/monitor.py` | 8080 |
| React operations console | `npm --prefix frontend run dev` | 5173 |
| Java execution engine (optional dry-run sidecar) | see below | 50051 |
| FastMCP tool server (optional) | `PYTHONPATH=/workspace .venv/bin/python src/mcp_server.py` | 8000 |

There is no systemd in this VM, so Postgres/Redis must be started manually (commands above)
after a cold boot. The DB role/database (`bot_admin` / `trading_bot`) and the SQLite file
(`data/trading_bot.db`) persist in the snapshot; recreate the role only if Postgres is empty:
`sudo -u postgres psql -c "CREATE ROLE bot_admin WITH LOGIN PASSWORD 'bot_dev_secret' SUPERUSER;"`
then `CREATE DATABASE trading_bot OWNER bot_admin;` and `PYTHONPATH=/workspace .venv/bin/python scripts/init_db.py`.

### `.env` gotchas (not committed; gitignored)

Copy `.env.template` to `.env`, then note these dev-critical deviations:

- `POSTGRES_PORT=5432` — the native Postgres install listens on 5432, not the template's `5433`.
- `POSTGRES_PASSWORD` and `DASHBOARD_TOKEN` must be non-default non-empty values or `Settings` refuses to load.
- Leave `TELEGRAM_BOT_TOKEN` empty. The template's default `your_bot_token` is NOT in the code's
  placeholder-skip set, so the monitor tries to reach Telegram at startup and hard-crashes with
  `telegram.error.InvalidToken`. Empty token => console-only mode.
- `DEV_MODE=true` uses 24/7 crypto proxy pairs and bypasses NYSE/NASDAQ market hours — needed for
  end-to-end testing when the market is closed.
- Alpaca/Polygon/OpenAI/Gemini keys can stay as placeholders in paper mode; `AlpacaProvider`
  will log recurring "Failed to fetch" errors (non-fatal — paper fills route through the shadow service).

### Running the backend

`python src/monitor.py` alone fails with `ModuleNotFoundError: No module named 'src'` because the
script's own dir shadows the repo root. Always run it with `PYTHONPATH=/workspace` (or `python -m src.monitor`).

### Dashboard login is fail-closed (important for UI testing)

`/api/auth/login` requires either (a) Telegram approval or (b) TOTP 2FA already enabled — there is
NO token-only fallback despite what `frontend/README.md` says. With Telegram disabled, bootstrap 2FA
once via the app's own manager, then log in with the dashboard token + a TOTP/backup code:

```python
# PYTHONPATH=/workspace .venv/bin/python
from src.services.dashboard_service import dashboard_service
t = dashboard_service.totp
s = t.initiate_setup()                 # returns secret + backup_codes (save these)
assert t.verify_setup(t.totp_token(s["secret"]))  # enables 2FA
```

The auth state is stored in the SQLite `dashboard_auth_state` table and read fresh per request, so a
separate process can seed it while the server runs. Backup codes are single-use; TOTP codes rotate
every 30s (verify window ±30s).

### Frontend

Install must use `--legacy-peer-deps` (matches CI): `react-sprite-animator` declares a React 17 peer
but the app is React 19. Vite proxies `/api`, `/stream`, `/ws` to `http://localhost:8080`, so no CORS
config is needed in dev.

### Java execution engine (optional)

No Gradle wrapper is committed; use a standalone Gradle 8.10.x. Build with
`gradle generateProto shadowJar --no-daemon`, then run the shaded jar with `DRY_RUN=true`. `gradle test`
uses Testcontainers and therefore requires Docker (not installed by default here).

### Broker-connected Alpaca paper mode (real orders, paper money)

To validate against Alpaca's paper endpoint (submits real orders to a paper account,
not the internal shadow service), set in `.env`:

- `PAPER_TRADING=false` (routes fills to the broker instead of the shadow service)
- `LIVE_CAPITAL_DANGER=true` (required by the config guard whenever `PAPER_TRADING=false`)
- `DEV_MODE=false` (real market data + real market hours)
- `BROKERAGE_PROVIDER=ALPACA`, `ALPACA_BASE_URL=https://paper-api.alpaca.markets`
- `IGNORE_UNMANAGED_POSITIONS=true` (tolerate positions in the paper account outside the bot ledger)
- Real `ALPACA_API_KEY` / `ALPACA_API_SECRET` from an Alpaca **paper** account (provide as Cursor secrets;
  injected env vars override the `.env` placeholders).

This resolves to runtime mode `ALPACA_PAPER` (`broker_paper_trading=true`). The monitor detects the
paper endpoint and automatically **skips** the live L2-entropy-baseline gate even though
`LIVE_CAPITAL_DANGER=true`, so no entropy seeding is needed. In production (non-DEV) mode the scanner
reserves active slots for crypto pairs and scans them 24/7 (equity pairs are skipped when the US market
is closed), so crypto pairs like `BTC-USD/ETH-USD` produce activity off-hours. Market data works via
yfinance fallback if `POLYGON_API_KEY` is absent; the AI agent ensemble degrades gracefully without
`OPENAI_API_KEY`/`GEMINI_API_KEY` but is higher-fidelity with them.

### Tests

- Backend: `PYTHONPATH=/workspace .venv/bin/python -m pytest tests/ -q --asyncio-mode=auto`
  (`conftest.py` seeds fake secrets; tests fall back to SQLite so a real Postgres password is not needed).
  Note: `tests/unit/test_orchestrator_mab.py::test_thompson_sampling_weight_allocation` is a randomized
  Thompson-sampling test that can fail when run with the full suite (shared RNG) but passes in isolation.
- Frontend: `npm --prefix frontend run lint | test | build`.
