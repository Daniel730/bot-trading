# Copilot / coding-agent instructions (bot-trading)

Alpha Arbitrage is a **statistical-arbitrage** monorepo: Python monitor + dashboard API, React ops console, optional Java gRPC dry-run sidecar, Redis/PostgreSQL/SQLite, Alpaca brokerage (Trading 212 / Web3 are legacy-disabled).

## Before any substantial work

1. Follow `docs/AGENT_WORKFLOW.md` (issues with `[Correção]` / `[Melhoria]` / `[Nova função]`, feature branch, PR `Fixes #N`).
2. Prefer paper defaults: `PAPER_TRADING=true`, Java `DRY_RUN=true`.
3. Never commit secrets (`.env`, API keys, tokens, TOTP seeds).
4. Use custom agents under `.github/agents/` when the task matches (trading safety, review, tests, ops).

## Architecture (short)

| Path | Role |
|---|---|
| `src/monitor.py` | Scan loop + execution coordination |
| `src/config.py` | Settings + safety validators |
| `src/services/` | Brokerage, risk, dashboard, shadow, persistence, telemetry |
| `src/agents/` | Runtime signal ensemble (see `docs/agents.md`) |
| `frontend/` | Operations console |
| `execution-engine/` | Java dry-run execution/audit |
| `infra/` | Docker Compose + ops probes |
| `tests/` | Pytest unit + integration |

Canonical docs: `docs/ARCHITECTURE.md`, `docs/STRATEGY.md`, `docs/OPERATIONS.md`, `docs/DECISIONS.md`. Repo maps: `AGENTS.md`, `docs/CLAUDE.md`, `GEMINI.md`.

## How to validate

```bash
PYTHONPATH=. pytest tests/unit -q --asyncio-mode=auto
PYTHONPATH=. pytest tests/integration -q --asyncio-mode=auto
cd frontend && npm ci --legacy-peer-deps && npm run lint && npm run test && npm run build
# Java optional: cd execution-engine && gradle test shadowJar --no-daemon
```

PR CI: `.github/workflows/ci.yml`. Deploy: `.github/workflows/deploy.yml` (release / manual dispatch to bot-server).

## Safe vs dangerous

**Safe to automate:** read code, tests, lint, docs, branches/PRs, paper/shadow validation, static review.

**Needs explicit human approval:** strategy/sizing/risk limit changes; enabling live trading; production credentials; production deploy; disabling safety/2FA/approval; re-enabling T212/Web3 or Java live brokerage; opening Redis/Postgres/MCP to non-loopback; wiping Docker volumes.

## Never break

- `signal_id` continuity on open/close/ledger paths
- Venue checks only via `BrokerageService.get_venue()`
- Dashboard auth fail-closed (no token-only sessions)
- MCP `execute_trade` remains reject-only
- Do not invent parallel APM stacks; follow the target table in `docs/AGENT_WORKFLOW.md` (#118–#135)

## PRs

Use `.github/PULL_REQUEST_TEMPLATE.md`. Keep changes scoped. Document intentional mode/risk changes in the Safety section.
