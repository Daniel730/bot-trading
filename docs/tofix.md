# Current Backlog And Open Risks

Last refreshed: 2026-07-03 (validation session — branch `dps_alpaca_audit`, working tree uncommitted).

This is the current human-readable backlog. Older audit files are preserved for context, but this file is the preferred short list.

## Highest Priority

1. **Live Java brokerage is intentionally blocked** — *blocked by design*
   `execution-engine/Application.java` refuses `DRY_RUN=false`. Keep it that way until a real, tested `LiveBroker` is wired with integration tests.

2. **Trading 212 timeout recovery cannot fully correlate broker orders** — *open / legacy*
   `BrokerageService` keeps a local `client_order_id`, but Trading 212's public order schema does not accept that field. Timeout recovery should be redesigned around broker-returned order ids or post-submit reconciliation that can reliably match ticker, signed quantity, timestamp, and price band.

3. **Partial fills are still not modeled end-to-end** — *open*
   The Python live path logs requested quantities after broker success. Add order-status polling or broker execution reports, then persist filled quantity, average fill price, and remaining quantity per leg.

4. **Live Web3 path needs production-grade wallet safeguards** — *blocked / legacy-disabled*
   Keep Web3 execution behind explicit operator configuration. Add allowance checks, quote/slippage previews, chain-id confirmation, nonce handling, and testnet/mainnet separation before meaningful capital.

## Reliability

5. **Requirements lock file** — *done*
   `requirements.lock` is used by CI, Docker (`infra/Dockerfile`), and docs. `requirements.txt` remains human-readable.

6. **Some diagnostic output bypasses structured logging** — *open*
   There are still `print()`/`System.err` style diagnostics in a few paths. Convert them to module loggers so dashboard log ingestion stays consistent.

7. **FastMCP and dashboard API are separate surfaces** — *open*
   `src/mcp_server.py` exposes tool calls on port `8000`; `dashboard_service` serves the operator API on `8080`. Review auth and exposure expectations before binding either port publicly.

8. **Pair universe is large and eligibility-driven** — *in progress / watch*
   Keep a close eye on startup time, provider rate limits, and rejection summaries after edits to `settings.ARBITRAGE_PAIRS`.

9. **Dashboard WebSocket shutdown / auth middleware** — *in progress (working tree)*
   Uncommitted changes in `dashboard_service.py` convert HTTP auth middleware to ASGI (covers WebSocket scope), harden accept/close error handling, and fix disconnect cleanup. Needs commit + manual dashboard smoke test.

10. **Dev startup with pre-existing Alpaca paper positions** — *in progress (working tree)*
    `IGNORE_UNMANAGED_POSITIONS=true` (default) lets the monitor start when the Alpaca paper account has positions not tracked in the bot ledger. Safer for local dev; set `false` before live unattended execution. Add to `.env.template` when committed.

11. **`DataService` eager Alpaca client init** - *open* — GitHub [#56](https://github.com/Daniel730/bot-trading/issues/56)
    Importing `monitor.py` / `data_service` fails without `ALPACA_API_KEY`/`ALPACA_API_SECRET`, even for paper-only pytest runs. Lazy-init or test-safe defaults would improve DX and CI ergonomics.

## Strategy And Data Quality

12. **Corporate actions are not a complete first-class invalidation path** — *open*
    Historical data uses adjusted series in many paths, but pair state should still be explicitly invalidated around splits, symbol changes, and special dividends.

13. **Market calendar handling is approximate by venue suffix** — *open*
    `monitor.get_market_config()` uses suffix-based windows. Add exchange calendars and holidays for robust multi-region operation.

14. **SEC/fundamental cache misses default to neutral** — *open*
    This keeps the hot path alive, but it can let structurally unknown names pass through unless other agents veto. Consider stricter policy for live mode.

15. **Whale watcher is legacy-inactive in the active runtime** — *blocked / future*
    The orchestrator reports this as `INACTIVE`. Restoring cache-backed whale analysis needs fresh tests for ingestion freshness, summaries, vetoes, and telemetry.

## Testing Gaps

16. **Alpaca live-path contract tests** — *partially done*
    `tests/unit/test_alpaca_provider.py` covers symbol normalization, notional/qty orders, timeout reconciliation, pending orders, and portfolio reads with mocks. Still missing end-to-end monitor + budget integration under fake Alpaca.

17. **Dashboard auth regression tests** — *partially done*
    Session/token tests exist; frontend Vitest still drifts from UI (SidebarNav footer stats, LoginView input type, startup progress thresholds). 12 frontend tests failed in Docker on 2026-07-03.

18. **Java gRPC health/status tests** - *partially done* — GitHub [#57](https://github.com/Daniel730/bot-trading/issues/57)
    Unit tests pass except `MockBrokerTest.execute_InsufficientDepth_Failure`. `ExecutionIntegrationTest` needs Testcontainers/DinD (fails when Gradle runs inside a plain Docker container without socket access).

19. **Pair-eligibility regression fixtures** — *partially done*
    `tests/unit/test_pair_eligibility.py` exists; expand US, XETRA, Euronext, LSE, HK, cross-currency, crypto, and mixed crypto/equity examples.

20. **Docker pytest must mount `infra/` for compose secret gates** — *open*
    Full-suite Docker runs without `-v infra:/app/infra` falsely fail `test_backend_compose_secrets.py`. Document in `docs/OPERATIONS.md` or bake `tests/` + `infra/` into a dev test image.

## Alpaca Paper Dev Readiness (2026-07-03)

| Check | Status |
|---|---|
| `BROKERAGE_PROVIDER=ALPACA` enforced | OK |
| Paper endpoint default `https://paper-api.alpaca.markets` | OK |
| `PAPER_TRADING=true` → shadow execution | OK |
| Alpaca provider unit tests (Docker, mocked) | 26/26 passed |
| Config/broker route tests | passed |
| Startup unmanaged-position guard | OK with `IGNORE_UNMANAGED_POSITIONS=true` |
| Local branch vs `origin/dps_alpaca_audit` | ~570 commits behind — track [#58](https://github.com/Daniel730/bot-trading/issues/58) |
| Compose `config` without `.env` | Fails until `POSTGRES_PASSWORD` set (expected) |


## GitHub Issues (2026-07-03)

| Item | Issue |
|------|-------|
| DataService eager Alpaca init | https://github.com/Daniel730/bot-trading/issues/56 |
| Java Testcontainers / MockBrokerTest | https://github.com/Daniel730/bot-trading/issues/57 |
| Branch ~570 commits behind origin/dps_alpaca_audit | https://github.com/Daniel730/bot-trading/issues/58 |

Skipped (fixes em curso na working tree): z-scores, wallet, pairs, Vitest drift, orchestrator SEC veto — sem issues novas.
