# Alpha Arbitrage Bot — Open-Source Statistical Arbitrage Trading Bot Framework

> Open-source statistical arbitrage trading bot framework in Python and Java for paired equities and crypto. Includes a Kalman-filter spread engine, multi-agent signal validation, paper trading, Trading 212, Alpaca, and Web3 connectors, a gRPC execution engine, and a React operations dashboard.

[![License](https://img.shields.io/github/license/Daniel730/bot-trading)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Daniel730/bot-trading?style=social)](https://github.com/Daniel730/bot-trading/stargazers)
[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-%E2%9D%A4-ea4aaa?logo=githubsponsors)](https://github.com/sponsors/Daniel730)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![Java](https://img.shields.io/badge/java-21-orange?logo=openjdk)](https://openjdk.org/)
[![React](https://img.shields.io/badge/react-19-61dafb?logo=react)](https://react.dev/)

Alpha Arbitrage is a **statistical-arbitrage trading bot** and research/execution stack for paired assets. The Python monitor scans an equity and crypto pair universe, runs **Kalman-filter spread logic**, asks a small **agent ensemble** to validate signals, and routes accepted trades to either paper shadow execution, the active equity broker (**Trading 212** or **Alpaca**), **Web3**, or the **Java gRPC execution engine** depending on mode and venue. A **React operations console** exposes telemetry, pairs, trade history, config, and health.

**Keywords:** statistical arbitrage, pairs trading, algorithmic trading bot, quantitative trading, Kalman filter, mean reversion, Python trading bot, Java gRPC trading engine, crypto arbitrage bot, equity arbitrage, paper trading, backtesting, Trading 212 API, Alpaca API, Web3 trading bot, FastMCP, React trading dashboard, open source trading framework.

> **Disclaimer:** This repository is **educational and experimental**. It is **not financial advice**, and live trading can lose capital quickly. Use paper trading and dry-run modes before risking real money.

## Table of Contents

- [Features](#features)
- [Project Map](#project-map)
- [Runtime Topology](#runtime-topology)
- [Quick Start](#quick-start)
- [Java Execution Engine](#java-execution-engine)
- [Docker](#docker)
- [Modes](#modes)
- [Test Commands](#test-commands)
- [Documentation](#more-docs)
- [Support the Project](#support-the-project)
- [License](#license)

## Features

- **Statistical arbitrage** signal engine with Kalman-filter spread estimation and entropy/risk gates.
- **Multi-agent validation** ensemble that vets signals before they reach execution.
- **Pluggable execution venues**: paper shadow, Trading 212, Alpaca, Web3 wallet/router, and a high-performance Java gRPC engine.
- **Operations console** built in React for live telemetry, pair management, trade history, and configuration.
- **FastMCP tool server** for assistant/AI integrations over SSE.
- **Production-ready infra** with Dockerfiles, Compose files, Redis idempotency, and PostgreSQL persistence.

## Project Map

| Project | Path | Purpose |
|---|---|---|
| Python trading backend | `src/` | Monitor loop, dashboard API, persistence, risk, brokerage, agents, telemetry |
| Java execution engine | `execution-engine/` | gRPC execution service with Redis idempotency, VWAP checks, slippage guards |
| React operations console | `frontend/` | Authenticated dashboard for telemetry, pairs, trade history, config, and health |
| Infrastructure | `infra/` | Dockerfiles, Compose files, redeploy helper, systemd unit |
| Operational docs | `docs/` | Architecture, operations, strategy, budget, agents, historical audits |
| Tests | `tests/`, `execution-engine/src/test/`, `frontend/src/**/*.test.tsx` | Python, Java, and frontend test suites |

## Runtime Topology

```text
React console (:5173 dev / :3000 docker)
        |
        v
Python dashboard API (:8080) <--> Redis
        |                         PostgreSQL
        |                         SQLite fallback/runtime state
        v
Python monitor loop ---- gRPC ---- Java execution engine (:50051)
        |
        +---- active equity broker (Trading 212 or Alpaca)
        +---- Web3 wallet/router
        +---- market data providers

FastMCP tool server (:8000) is a separate optional SSE endpoint for assistant/tool integrations.
```

## Quick Start

1. Create local configuration:

```bash
cp .env.template .env
```

Set at least `POSTGRES_PASSWORD` and `DASHBOARD_TOKEN` to non-default secret values. Add market data, Telegram, broker, OpenAI/Gemini, and Web3 credentials only for the paths you intend to use.

For live equity execution, choose one active broker:

```bash
BROKERAGE_PROVIDER=T212      # Trading 212
# BROKERAGE_PROVIDER=ALPACA  # Alpaca paper/live endpoint from ALPACA_BASE_URL
```

`BROKERAGE_PROVIDER=ALPACA` uses `ALPACA_API_KEY`, `ALPACA_API_SECRET`, and `ALPACA_BASE_URL`; the template defaults Alpaca to the paper endpoint.

2. Install and initialize the Python backend:

```bash
pip install -r requirements.txt
python scripts/init_db.py
```

3. Start the monitor. This also starts the dashboard API on port `8080`:

```bash
python src/monitor.py
```

4. Start the frontend in another shell:

```bash
cd frontend
npm install
npm run dev
```

Vite uses port `5173` by default. The app automatically talks to `http://localhost:8080` when running locally.

5. Optional: start the standalone FastMCP tool server:

```bash
python src/mcp_server.py
```

It runs on port `8000` with SSE transport.

## Java Execution Engine

The Java service requires Java 21 and Gradle:

```bash
cd execution-engine
gradle generateProto --no-daemon
gradle shadowJar --no-daemon
gradle test --no-daemon
```

Run the jar with `DRY_RUN=true`:

```powershell
$env:DRY_RUN="true"
java -jar build/libs/execution-engine-1.0-SNAPSHOT-all.jar
```

`DRY_RUN=true` is required today. The service intentionally refuses to boot with `DRY_RUN=false` until a real live Java broker implementation is wired.

## Docker

Production compose pulls GHCR images:

```bash
docker compose -f infra/docker-compose.yml up -d
```

For local builds on your machine:

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.local.yml \
  up -d --build --remove-orphans
```

Useful ports:

| Port | Service |
|---|---|
| `3000` | Docker frontend nginx |
| `8080` | Python dashboard/API |
| `8000` | optional FastMCP SSE tool server |
| `50051` | Java gRPC execution engine |
| `6379` | Redis |
| `5433` | PostgreSQL exposed on host |

## Modes

| Setting | Effect |
|---|---|
| `PAPER_TRADING=true` | Uses shadow execution and does not submit live broker orders |
| `BROKERAGE_PROVIDER=T212` | Selects the live equity broker for non-crypto tickers (`T212` or `ALPACA`) |
| `DEV_MODE=true` | Uses crypto test pairs, bypasses equity market hours, and enables development behavior |
| `DRY_RUN=true` | Keeps the Java engine in mock-broker mode |
| `LIVE_CAPITAL_DANGER=true` | Refuses startup unless Redis L2 entropy baselines exist |
| `ALLOW_LIVE_APPROVAL_WITHOUT_TELEGRAM=false` | Requires Telegram approval wiring for live approvals |

## Test Commands

```bash
pytest tests/ -v --asyncio-mode=auto

cd execution-engine
gradle test --no-daemon

cd frontend
npm run lint
npm run test
npm run build
```

## More Docs

Start with [docs/README.md](docs/README.md), then use:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system design.
- [docs/OPERATIONS.md](docs/OPERATIONS.md) for day-to-day running.
- [docs/STRATEGY.md](docs/STRATEGY.md) for signal and risk logic.
- [src/README.md](src/README.md), [frontend/README.md](frontend/README.md), [execution-engine/README.md](execution-engine/README.md), and [infra/README.md](infra/README.md) for per-project details.

## Support the Project

If Alpha Arbitrage Bot saves you time or helps your research, please consider supporting development. Sponsorships fund infrastructure costs (databases, market-data feeds, CI), new venue integrations, and continued maintenance.

[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor%20on%20GitHub-%E2%9D%A4-ea4aaa?style=for-the-badge&logo=githubsponsors)](https://github.com/sponsors/Daniel730)

You can also help by:

- Starring the repo on [GitHub](https://github.com/Daniel730/bot-trading) — it boosts discoverability.
- Sharing the project with traders, quants, or developers who might benefit.
- Filing high-quality issues or pull requests.

## FAQ

**What is Alpha Arbitrage Bot?**
It is an open-source framework for building and running **statistical arbitrage / pairs-trading** strategies across equities and crypto, with paper-trading and live-broker execution paths.

**What languages and stack does it use?**
Python 3.10+ for the monitor, signal engine, dashboard API, and agent ensemble; Java 21 for the gRPC execution engine; React 19 + Vite for the operations console; PostgreSQL and Redis for persistence and idempotency.

**Can I use it for live trading?**
Yes, but only after extensive paper trading. The Java engine ships in `DRY_RUN` mode and intentionally refuses to boot live until a real broker implementation is wired. Read [docs/OPERATIONS.md](docs/OPERATIONS.md) and [docs/STRATEGY.md](docs/STRATEGY.md) first.

**Is this financial advice?**
No. It is an educational and experimental project. Trading involves risk of loss.

## License

See [LICENSE](LICENSE) for details. Issues and pull requests are welcome on [GitHub](https://github.com/Daniel730/bot-trading).

---

<sub>Topics: <code>trading-bot</code> · <code>statistical-arbitrage</code> · <code>pairs-trading</code> · <code>algorithmic-trading</code> · <code>quantitative-finance</code> · <code>kalman-filter</code> · <code>python</code> · <code>java</code> · <code>grpc</code> · <code>crypto</code> · <code>trading-212</code> · <code>alpaca</code> · <code>web3</code> · <code>react-dashboard</code> · <code>open-source</code></sub>
