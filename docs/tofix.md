# Current Backlog And Open Risks

Last refreshed: 2026-08-10 (documentation sync vs `master`; statuses re-checked against code/issues).

This is the current human-readable backlog. Older audit files are preserved for context, but this file is the preferred short list. Prefer GitHub issues with `[Correção]` / `[Melhoria]` / `[Nova função]` for new work (`docs/AGENT_WORKFLOW.md`).

Historical registers (`docs/bugs.md`, `.brain/*`) contain many items marked **Persists** that are already fixed in code — do not treat them as open without re-verifying source.

## Highest Priority

1. **Live Java brokerage is intentionally blocked** — *blocked by design*
   `execution-engine/Application.java` refuses `DRY_RUN=false`. Keep it that way until a real, tested `LiveBroker` is wired with integration tests. Live Alpaca execution is Python-only today.

2. **Trading 212 timeout recovery cannot fully correlate broker orders** — *open / legacy*
   Active runtime is Alpaca-only (`BROKERAGE_PROVIDER=ALPACA`). T212 recovery code remains in repo but is not on the live path. Alpaca ambiguous-submit recovery uses `client_order_id` derived from `signal_id` (`{signal_id}-A`/`-B`); monitor still needs manual reconciliation when reconciliation fails.

3. **Partial fills are still not modeled end-to-end** — *open* — GitHub [#89](https://github.com/Daniel730/bot-trading/issues/89)
   Monitor detects `partially_filled` on Leg A, emergency-closes, and blocks with `PARTIAL_EXPOSURE` / `NEEDS_MANUAL_RECONCILIATION`. Ledger rows still do not persist average fill price and remaining quantity per leg across the full open/close lifecycle.

4. **Live Web3 path needs production-grade wallet safeguards** — *blocked / legacy-disabled*
   `BROKERAGE_PROVIDER=WEB3` fails startup. Legacy code remains in repo.

## Reliability

5. **Requirements lock file** — *done*
   `requirements.lock` is used by CI, Docker (`infra/Dockerfile`), and docs. `requirements.txt` remains human-readable.

6. **Some diagnostic output bypasses structured logging** — *open* — GitHub [#90](https://github.com/Daniel730/bot-trading/issues/90)
   Residual `print()` in services/agents; convert to module loggers for consistent dashboard log ingestion.

7. **FastMCP and dashboard API are separate surfaces** — *open / by design*
   FastMCP on `:8000`, dashboard API on `:8080`. Compose publishes MCP on loopback only.

8. **Pair universe is large and eligibility-driven** — *watch*
   Watch startup time, provider rate limits, and rejection summaries after edits to `settings.ARBITRAGE_PAIRS`.

9. **Dashboard WebSocket shutdown / auth middleware** — *done*
   ASGI-native `DashboardAuthMiddleware` covers HTTP + WebSocket.

10. **Dev startup with pre-existing Alpaca paper positions** — *done*
    `IGNORE_UNMANAGED_POSITIONS=true` (default in `.env.template`). Set `false` before live unattended execution.

11. **`DataService` eager Alpaca client** — *done* — GitHub [#56](https://github.com/Daniel730/bot-trading/issues/56)
    Lazy client on first `alpaca_client` access.

12. **Compose bot restart after host reboot** — *done* — GitHub [#137](https://github.com/Daniel730/bot-trading/issues/137) / [#138](https://github.com/Daniel730/bot-trading/pull/138)
    `bot` / `sec-worker` / `frontend` / `execution-engine` → `unless-stopped`; Redis/Postgres → `always`; optional `mcp-server` → `no`.

## Strategy And Data Quality

13. **Corporate actions are not a complete first-class invalidation path** — *open*
    Jump gate via `CORP_ACTION_PRICE_JUMP_PCT` exists; broader split/symbol-change workflow still needed.

14. **Market calendar handling is approximate by venue suffix** — *open*
    `monitor.get_market_config()` uses suffix-based windows.

15. **SEC/fundamental cache misses default to neutral in paper mode** — *by design*
    Live (`PAPER_TRADING=false`) vetoes unknown scores; paper keeps `ORCH_FUNDAMENTAL_DEFAULT_SCORE`.

16. **Whale watcher is legacy-inactive** — *dormant by design* — GitHub [#91](https://github.com/Daniel730/bot-trading/issues/91)
    Stub reports `INACTIVE`; `WHALE_WATCHER_ENABLED` alone does not activate.

17. **Bull/bear theme agents** — *mitigated*
    Heuristic stubs by default; optional LLM behind `BULL_BEAR_LLM_ENABLED=false` + caps.

## Testing Gaps

18. **Alpaca live-path contract tests** — *partial*
19. **Dashboard auth / frontend Vitest** — *partial* (~16 frontend tests)
20. **Java gRPC integration tests** — *partial* — GitHub [#57](https://github.com/Daniel730/bot-trading/issues/57)
21. **Pair-eligibility regression fixtures** — *partial*
22. **Docker pytest must mount `infra/` for compose secret gates** — *documented* in `docs/OPERATIONS.md` (Pytest In Docker); keep CI/Docker runners aware — related [#59](https://github.com/Daniel730/bot-trading/issues/59)

## Platform / observability targets

Foundation issues **#118–#135** (OTel, Sentry, Datadog, Biome, Ruff, Codecov, Playwright, dedicated CI, skeletons, lazy panels, motion). Documented as **targets** in `docs/AGENT_WORKFLOW.md` — internal `telemetry_service` exists; vendor APM does **not**.

## Documentation

- Prior broker/whale doc drift tracked in [#60](https://github.com/Daniel730/bot-trading/issues/60) (closed).
- Full docs sync: [#139](https://github.com/Daniel730/bot-trading/issues/139).

## Prioritized functionality backlog

1. End-to-end partial-fill ledger modeling ([#89](https://github.com/Daniel730/bot-trading/issues/89)).
2. Alpaca ambiguous-submit / timeout reconciliation hardening + operator playbook.
3. Broker/ledger reconciliation for unattended live (`IGNORE_UNMANAGED_POSITIONS=false` only after import/close).
4. Corporate-action pair invalidation beyond jump gate.
5. Exchange calendar accuracy.
6. Java dry-run integration tests ([#57](https://github.com/Daniel730/bot-trading/issues/57)).
7. Monitor + Alpaca fake-broker integration test.
8. Platform observability/quality stack ([#118](https://github.com/Daniel730/bot-trading/issues/118)–[#135](https://github.com/Daniel730/bot-trading/issues/135)).
