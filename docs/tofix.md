# Current Backlog And Open Risks

Last refreshed: 2026-07-05 (full doc audit + code cross-check; branch `dps_alpaca_audit`, working tree uncommitted).

This is the current human-readable backlog. Older audit files are preserved for context, but this file is the preferred short list.

Historical registers (`docs/bugs.md`, `.brain/*`) contain many items marked **Persists** that are already fixed in code — do not treat them as open without re-verifying source.

## Highest Priority

1. **Live Java brokerage is intentionally blocked** — *blocked by design*
   `execution-engine/Application.java` refuses `DRY_RUN=false`. Keep it that way until a real, tested `LiveBroker` is wired with integration tests. Live Alpaca execution is Python-only today.

2. **Trading 212 timeout recovery cannot fully correlate broker orders** — *open / legacy*
   Active runtime is Alpaca-only (`BROKERAGE_PROVIDER=ALPACA`). T212 recovery code remains in repo but is not on the live path. Alpaca ambiguous-submit recovery uses `client_order_id` derived from `signal_id` (`{signal_id}-A`/`-B`); monitor still needs manual reconciliation when reconciliation fails.

3. **Partial fills are still not modeled end-to-end** — *open (partial mitigation)*
   Monitor detects `partially_filled` on Leg A, emergency-closes, and blocks with `PARTIAL_EXPOSURE` / `NEEDS_MANUAL_RECONCILIATION`. Ledger rows still do not persist average fill price and remaining quantity per leg across the full open/close lifecycle.

4. **Live Web3 path needs production-grade wallet safeguards** — *blocked / legacy-disabled*
   Keep Web3 execution behind explicit operator configuration. `BROKERAGE_PROVIDER=WEB3` fails startup. Legacy code remains in repo.

## Reliability

5. **Requirements lock file** — *done*
   `requirements.lock` is used by CI, Docker (`infra/Dockerfile`), and docs. `requirements.txt` remains human-readable.

6. **Some diagnostic output bypasses structured logging** — *open*
   `print()` remains in `notification_service.py`, `risk_service.py`, `sec_service.py`, and `fundamental_analyst.py`. Convert to module loggers so dashboard log ingestion stays consistent.

7. **FastMCP and dashboard API are separate surfaces** — *open*
   `src/mcp_server.py` exposes tool calls on port `8000`; `dashboard_service` serves the operator API on `8080`. Review auth and exposure expectations before binding either port publicly.

8. **Pair universe is large and eligibility-driven** — *in progress / watch*
   Keep a close eye on startup time, provider rate limits, and rejection summaries after edits to `settings.ARBITRAGE_PAIRS`.

9. **Dashboard WebSocket shutdown / auth middleware** — *done (working tree, uncommitted)*
   `DashboardAuthMiddleware` is ASGI-native (covers HTTP + WebSocket scope). WebSocket accept/close and disconnect cleanup hardened. Needs commit + manual dashboard smoke test.

10. **Dev startup with pre-existing Alpaca paper positions** — *done (working tree, uncommitted)*
    `IGNORE_UNMANAGED_POSITIONS=true` (default) lets the monitor start when the Alpaca paper account has positions not tracked in the bot ledger. Documented in `.env.template` (working tree). Set `false` before live unattended execution.

11. **`DataService` eager Alpaca client on first use** — *partially done* — GitHub [#56](https://github.com/Daniel730/bot-trading/issues/56)
    Module singleton is lazy (`_LazyDataService` since 2026-05-21): importing `monitor.py` no longer constructs Alpaca at import time. `DataService.__init__` still eagerly builds `tradeapi.REST` on first real use; direct `DataService()` in tests still needs `ALPACA_API_KEY`/`ALPACA_API_SECRET`.

## Strategy And Data Quality

12. **Corporate actions are not a complete first-class invalidation path** — *open*
    Historical data uses adjusted series in many paths, but pair state should still be explicitly invalidated around splits, symbol changes, and special dividends.

13. **Market calendar handling is approximate by venue suffix** — *open*
    `monitor.get_market_config()` uses suffix-based windows. Add exchange calendars and holidays for robust multi-region operation.

14. **SEC/fundamental cache misses default to neutral in paper mode** — *by design (working tree)*
    Orchestrator now fail-closed on unknown fundamental scores only when `PAPER_TRADING=false` (live broker path). Paper/shadow mode keeps `ORCH_FUNDAMENTAL_DEFAULT_SCORE` so SEC worker downtime does not block paper validation. Live mode still vetoes missing scores — covered by `tests/unit/test_orchestrator_fundamentals.py` (working tree).

15. **Whale watcher is legacy-inactive in the active runtime** — *blocked / future*
    The orchestrator reports whale verdict as `INACTIVE`. Restoring cache-backed whale analysis needs fresh tests for ingestion freshness, summaries, vetoes, and telemetry.

## Testing Gaps

16. **Alpaca live-path contract tests** — *partially done*
    `tests/unit/test_alpaca_provider.py` covers symbol normalization, notional/qty orders, timeout reconciliation, pending orders, and portfolio reads with mocks. Still missing end-to-end monitor + budget integration under fake Alpaca.

17. **Dashboard auth regression tests** — *in progress (working tree)*
    Session/token tests exist. Frontend Vitest drift fixes underway: `SidebarNav.test.tsx`, `LoginView.test.tsx`, `runtimeUrl.test.ts`, `useStartupProgress.ts`. Could not re-run `npm test` locally (npm unavailable in audit shell).

18. **Java gRPC health/status tests** - *partially done* — GitHub [#57](https://github.com/Daniel730/bot-trading/issues/57)
    `MockBrokerTest.execute_InsufficientDepth_Failure` still expects message containing `"market depth"`. `ExecutionIntegrationTest` needs Testcontainers/DinD (fails when Gradle runs inside a plain Docker container without socket access).

19. **Pair-eligibility regression fixtures** — *partially done*
    `tests/unit/test_pair_eligibility.py` exists; expand US, XETRA, Euronext, LSE, HK, cross-currency, crypto, and mixed crypto/equity examples.

20. **Docker pytest must mount `infra/` for compose secret gates** — *open* — GitHub [#59](https://github.com/Daniel730/bot-trading/issues/59)
    Full-suite Docker runs without `-v infra:/app/infra` falsely fail `test_backend_compose_secrets.py`. Not yet documented in `docs/OPERATIONS.md`.

## Documentation Drift (verified 2026-07-05)

| Doc | Problem | Code truth |
|-----|---------|------------|
| `src/README.md` § Core Flow step 7 | Says live mode routes to "Trading 212 or Alpaca" or Web3 by venue | Alpaca-only; T212/Web3 fail startup |
| `docs/agents.md` § Whale Watcher | Describes active veto/confidence behavior | Runtime reports `INACTIVE` / legacy-neutral |
| `docs/CLAUDE.md` § Signal Flow step 7 | Says live uses `T212/Alpaca/Web3` | Alpaca-only active path |
| `frontend/README.md` § Pairs screen | "T212 wallet seeding" | Renamed to broker wallet sync (`syncWallet`) |
| `docs/bugs.md` | Many **Persists** / **New** items from 2026-04-12 | Historical; several fixed (sector mapping, cash mgmt await, secret guards, idempotency via `signal_id` client_order_id) |

Tracked in GitHub [#60](https://github.com/Daniel730/bot-trading/issues/60).

## Alpaca Paper Dev Readiness (2026-07-05)

| Check | Status |
|---|---|
| `BROKERAGE_PROVIDER=ALPACA` enforced | OK |
| Paper endpoint default `https://paper-api.alpaca.markets` | OK |
| `PAPER_TRADING=true` → shadow execution | OK |
| `IGNORE_UNMANAGED_POSITIONS` in `.env.template` | OK (working tree) |
| Orchestrator live fundamental veto | OK (working tree + tests) |
| Monitor z-score cost scaling (`monitor_helpers.compute_entry_zscore`) | OK (working tree) |
| Local branch vs `origin/dps_alpaca_audit` | **570 commits behind** — [#58](https://github.com/Daniel730/bot-trading/issues/58) |
| Compose `config` without `.env` | Fails until `POSTGRES_PASSWORD` set (expected) |

## GitHub Issues (2026-07-05)

| Item | Issue |
|------|-------|
| DataService eager Alpaca on first use | https://github.com/Daniel730/bot-trading/issues/56 |
| Java Testcontainers / MockBrokerTest | https://github.com/Daniel730/bot-trading/issues/57 |
| Branch ~570 commits behind origin/dps_alpaca_audit | https://github.com/Daniel730/bot-trading/issues/58 |
| Docker pytest infra mount undocumented | https://github.com/Daniel730/bot-trading/issues/59 |
| Doc-code drift (broker routing, whale watcher) | https://github.com/Daniel730/bot-trading/issues/60 |

Skipped (fixes em curso na working tree, sem issues novas): dashboard WebSocket ASGI auth, `IGNORE_UNMANAGED_POSITIONS`, orchestrator SEC live veto, z-score cost ceiling, wallet/pairs UI renames.

## Prioritized Functionality-Only Backlog (trade correctly)

1. **Sync branch with `origin/dps_alpaca_audit`** ([#58](https://github.com/Daniel730/bot-trading/issues/58)) — 570 commits behind; risk of missing remote fixes before any live validation.
2. **Commit and validate working-tree trading fixes** — live fundamental veto, z-score cost scaling, `IGNORE_UNMANAGED_POSITIONS`, dashboard WebSocket auth (paper smoke + one live-config dry run).
3. **End-to-end partial-fill ledger modeling** — poll order status, persist `filled_qty`/avg price/remaining per leg through open and close.
4. **Alpaca ambiguous-submit / timeout reconciliation hardening** — verify `{signal_id}-A/B` client_order_id paths under simulated timeouts; document operator playbook when `NEEDS_MANUAL_RECONCILIATION` fires.
5. **Broker/ledger reconciliation for unattended live** — set `IGNORE_UNMANAGED_POSITIONS=false` only after import/close of foreign positions; expand startup audit UX.
6. **Corporate-action pair invalidation** — suspend pairs on splits/symbol changes instead of silently using stale Kalman state.
7. **Exchange calendar accuracy** — replace suffix-only market windows so equity pairs are not scanned or traded outside real sessions.
8. **Live-mode SEC fundamental guard** — ensure SEC worker freshness + Redis cache population before `PAPER_TRADING=false` unattended runs (orchestrator logic done; ops wiring remains).
9. **Java dry-run integration tests** ([#57](https://github.com/Daniel730/bot-trading/issues/57)) — Testcontainers/DinD or documented skip; fix `MockBrokerTest` depth assertion.
10. **Monitor + Alpaca fake-broker integration test** — full signal → approval → two-leg submit → ledger row contract under mocks (closes gap in item 16).
