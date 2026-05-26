# Fix Priority Queue

Last updated: 2026-05-26

## P0 - Must fix before broker-connected testing

- Runtime dependencies are currently unavailable locally: Docker, Redis, Postgres, dashboard, and execution-engine preflight checks failed on 2026-05-19.
- DONE 2026-05-19: backend Compose now has a tested fail-fast Postgres password guard and no hardcoded/default fallback password.
- DONE 2026-05-19: Telegram notification exception output now redacts bot tokens and Telegram API bot URLs before printing/logging.
- DONE 2026-05-19: local historical `logs/recovery_window.log` was sanitized and a regression now catches direct or wrapped Telegram bot token leaks when that ignored log file exists.
- DONE 2026-05-20: Telegram/httpx request logs now redact bot API URLs before console/log handlers can print the bot token.
- DONE 2026-05-20: Telegram operational alerts retry as plain text when Markdown parsing rejects reconciliation/status messages.
- EXTERNAL ACTION REQUIRED: rotate the leaked Telegram bot token in BotFather/secrets before any operator-facing launch; repository code cannot revoke the old token.
- DONE 2026-05-19: crypto spread-guard bid/ask sourcing now falls back to Alpaca crypto snapshot quotes when yfinance reports zero bid/ask, while still failing closed if no positive quote exists.
- DONE 2026-05-20: crypto bid/ask fallback no longer passes unsupported `exchange=` to Alpaca `get_crypto_snapshots()`, fixing zero-quote spread-guard rejects caused by SDK signature mismatch.
- DONE 2026-05-20: latest crypto price snapshots no longer pass unsupported `exchange=` to Alpaca `get_crypto_snapshots()`, preventing valid paper Alpaca crypto prices from falling through to the concurrent yfinance fallback.
- DONE 2026-05-20: monitor entries now fail closed on invalid Kalman state before Redis persistence, AI approval, or execution when beta is clipped, z-score/state values are non-finite, innovation variance is invalid, or z-score is absurd.
- DONE 2026-05-20: invalid Kalman state now quarantines the affected pair, drops poisoned in-memory/Redis Kalman state, and keeps entries blocked until the existing historical initialization path rebuilds that pair.
- DONE 2026-05-20: newly quarantined Kalman pairs now request a post-scan historical rebuild/reload, so pairs such as BTC-USD/LTC-USD do not remain skipped forever while still blocking entries until rebuild completes.
- DONE 2026-05-20: crypto latest prices now pass coarse per-symbol sanity checks before Kalman update, blocking impossible cross-assigned prices such as BTC near $9 or ETH near BTC prices before state can be poisoned.
- DONE 2026-05-20: chunked latest-price fetches now serialize crypto chunks, preventing concurrent yfinance crypto fallback calls from cross-assigning ticker prices when Alpaca/Polygon do not fill the batch.
- DONE 2026-05-20: trade decision reports now include latest price values, price source labels, and explicit rejection reasons per pair so skipped/blocked trades are easier to audit.
- DONE 2026-05-20: trade decision reports now include loaded-but-not-scanned pairs with reasons such as `market_closed` or `not_cointegrated`, explaining gaps like `Scanned: 9/16`.
- DONE 2026-05-20: spread-guard blocks now carry bid/ask values, leg spread percentages, total spread percentage, and configured max spread into execution diagnostics and trade decision reports.
- DONE 2026-05-20: unprofitable profit-guard vetoes now carry gross profit, friction, net profit, sizing, z-score, and spread inputs into execution diagnostics and trade decision reports.
- DONE 2026-05-20: profit-preview math now fails closed when a candidate entry is already at or beyond the configured statistical stop-loss z-score instead of showing positive expected profit with zero loss risk.
- DONE 2026-05-20: repeated unchanged Alpaca crypto snapshot price tuples now fail closed before Kalman updates so stale live-data snapshots cannot create or preserve bad signal state.
- DONE 2026-05-20: latest crypto prices now use newer Alpaca quote midpoints, with quote source and timestamp metadata, when the snapshot trade price is older than the quote.
- DONE 2026-05-20: repeated unchanged Alpaca crypto quote-mid timestamps now fail closed before Kalman updates, preventing frozen quote midpoint data from silently driving signal math.
- DONE 2026-05-20: chunked async latest-price reads now mark Redis-cache hits as `redis` and clear old Alpaca timestamps, preventing cached prices from being falsely blocked as repeated Alpaca quote-mid snapshots.
- DONE 2026-05-25: sync latest-price cache writes scheduled from `_run_sync_backend` worker threads now target the caller's running event loop instead of `asyncio.get_event_loop()` in the worker, preventing dropped Redis warmup writes on Python 3.14+.
- DONE 2026-05-20: crypto snapshot stale-repeat cadence is now intentionally pinned at 5 scans and covered by a regression test, resolving the dirty runtime/test mismatch.
- DONE 2026-05-20: compose files are pinned to LF line endings and normalized, resolving noisy dirty compose diffs without runtime behavior changes.
- DONE 2026-05-20: trade decision reports now include per-leg latest price timestamps, making quote-mid freshness visible in every scan report.
- DONE 2026-05-20: local Docker runtime was rebuilt from current code, `.env` was repaired from stale `POSTGRES_PASSWORD=bot_pass`/`DATABASE_URL` defaults to the existing Postgres volume secret, and live decision reports confirmed `alpaca_crypto_quote_mid` price sources plus per-leg price timestamps.
- DONE 2026-05-21: L2 entropy baseline startup guard now skips Alpaca paper broker mode (`PAPER_TRADING=false` with the Alpaca paper endpoint) while still requiring baselines for actual live endpoints, preventing paper-broker boot refusal as "LIVE mode".
- DONE 2026-05-21: Docker `sec-worker` now overrides host-side `.env` Postgres settings with Compose dependency host `postgres:5432`, fixing container failures that tried `localhost:5433`.
- DONE 2026-05-21: Docker `execution-engine` is pinned to dry-run sidecar mode (`DRY_RUN=true`, `LIVE_CAPITAL_DANGER=false`) so Python Alpaca paper broker mode can use `LIVE_CAPITAL_DANGER=true` without the Java sidecar blocking startup on live entropy baselines.
- DONE 2026-05-22: execution-engine client dispatch now reacquires an atomic Redis `SET NX` lock per `signal_id` before reading/writing idempotency state or submitting `ExecuteTrade`, so concurrent workers fail closed instead of duplicating broker orders.
- DONE 2026-05-21: Broker/ledger mismatch startup blocks now include a read-only reconciliation audit for every nonzero broker position, including quantity, available quantity, current price, market value, ledger match, matched signal IDs, and a safe operator action.
- BLOCKED 2026-05-21: Alpaca paper broker startup now reaches health checks, then correctly fails closed on broker/ledger mismatch because the paper account has unmanaged positions (`ADA-USD`, `AVAX-USD`, `BCH-USD`, `BTC-USD`, `DOT-USD`, `ETH-USD`, `LINK-USD`, `LTC-USD`, `SOL-USD`). Resolve by importing, closing, or otherwise reconciling broker positions before scans resume.
- DONE 2026-05-19: completed scan iterations now append durable JSONL trade decision reports under `logs/trade_decision_reports.jsonl`.

## P1 - Must fix before extended personal testing

- DONE 2026-05-19: dashboard runtime config updates now validate the resulting `Settings` guardrails before persisting; unsafe `PAPER_TRADING=false` with `LIVE_CAPITAL_DANGER=false` is rejected.
- DONE 2026-05-19: `process_pair()` diagnostics and trade decision reports now include skip reasons such as `market_closed`, `not_cointegrated`, `missing_price`, `kalman_unavailable`, and `below_entry_threshold`.
- DONE 2026-05-19: paper shadow entries now write `TradeJournal` context before shadow ledger execution, including z-score, entry threshold, confidence, verdict, regime, and sizing metrics.
- DONE 2026-05-19: architecture docs/tests now state that `src/monitor.py` paper orders use `shadow_service`, broker-connected orders use Python `BrokerageService`, and the Java execution engine is a dry-run/audit sidecar rather than the monitor's default order path.
- DONE 2026-05-19: dashboard wallet buy endpoints now fail closed with HTTP 409 while `PAPER_TRADING=true` instead of returning fake successful paper order IDs that never reach Alpaca.
- DONE 2026-05-20: dashboard Pairs and Wallet buy buttons now honor the live `PAPER_TRADING` runtime/config state, disable broker-buy actions in shadow paper mode, and show the same fail-closed message as the backend before any confirm dialog or buy API call.
- DONE 2026-05-20: dashboard runtime mode now distinguishes local shadow paper (`PAPER_TRADING=true`) from broker-connected Alpaca paper (`PAPER_TRADING=false` with `ALPACA_BASE_URL=https://paper-api.alpaca.markets`) by reporting `ALPACA_PAPER` instead of plain `LIVE`.
- DONE 2026-05-20: dashboard Settings metadata now explains that `PAPER_TRADING=true` is local shadow mode, while Alpaca paper broker orders require `PAPER_TRADING=false` with `ALPACA_BASE_URL=https://paper-api.alpaca.markets`.
- DONE 2026-05-20: startup preflight logs and `/api/system/health` now expose sanitized runtime mode fields (`execution_mode`, `broker_paper_trading`, and `alpaca_endpoint_class`) so Docker logs and health payloads show shadow, Alpaca paper, or live posture without leaking the raw Alpaca URL.
- DONE 2026-05-20: System Health now displays sanitized runtime mode fields (`execution_mode`, broker-paper flag, and Alpaca endpoint class) from `/api/system/health`, so operators can verify shadow, Alpaca paper, or live posture from the dashboard.
- DONE 2026-05-21: `src.services.data_service` no longer initializes Polygon/Alpaca clients at module import; the public `data_service` singleton is lazy and only creates `DataService` on first real use.
- DONE 2026-05-21: `MacroEconomicAgent` no longer constructs `DataService` during module-level singleton import; market-data clients are created only when the agent first needs historical data.
- DONE 2026-05-21: `PortfolioManagerAgent` no longer constructs `DataService` during module-level singleton import; market-data clients are created only when portfolio optimization/discovery first needs historical data.
- DONE 2026-05-21: `src.services.brokerage_service` no longer initializes `AlpacaProvider` at module import; the public `brokerage_service` singleton is lazy and only creates `BrokerageService` on first real brokerage use.
- DONE 2026-05-21: `src.services.redis_service` no longer initializes a Redis client at module import; the public `redis_service` singleton is lazy and only creates `RedisService` on first real Redis use.
- DONE 2026-05-21: tests that exercise imported module singletons now patch the target used by the module under test (`src.monitor.*`, `NotificationService`'s runtime brokerage import, and `src.agents.orchestrator.macro_economic_agent`), eliminating order-dependent real service calls after module reloads.
- DONE 2026-05-21: official reusable fake fixtures now exist for broker, market data, Redis, and persistence boundaries via `tests/conftest.py` and `tests/fakes.py`, giving future tests a shared isolation layer instead of ad hoc real-service patches.
- DONE 2026-05-25: pytest now excludes `live`, `benchmark`, and `redis_real` markers from the default suite, with explicit marker registration and known live/benchmark tests marked for opt-in runs.
- DONE 2026-05-25: startup guard tests now construct `ArbitrageMonitor` through an isolated fake-broker factory, with a guard test preventing direct monitor construction from reintroducing real brokerage initialization cost.
- DONE 2026-05-25: startup broker/ledger mismatch tests are split out of the `test_startup_guards.py` monolith into `tests/unit/test_startup_broker_ledger_mismatch.py`, with a layout guard covering the boundary.
- DONE 2026-05-25: startup unresolved execution-state tests are split out of the `test_startup_guards.py` monolith into `tests/unit/test_startup_unresolved_execution_state.py`, with the startup contract layout guard covering the boundary.
- DONE 2026-05-25: startup entropy baseline tests are split out of the `test_startup_guards.py` monolith into `tests/unit/test_startup_entropy_baselines.py`, with the startup contract layout guard covering the boundary.
- DONE 2026-05-25: startup health-check failure tests for PostgreSQL, Redis, and Alpaca are split out of the `test_startup_guards.py` monolith into `tests/unit/test_startup_health_checks.py`, with the startup contract layout guard covering the boundary.
- DONE 2026-05-25: startup database initialization failure tests are split out of the `test_startup_guards.py` monolith into `tests/unit/test_startup_database_initialization.py`, with the startup contract layout guard covering the boundary.
- DONE 2026-05-25: startup no-scannable-pairs tests are split out of the `test_startup_guards.py` monolith into `tests/unit/test_startup_no_scannable_pairs.py`, with the startup contract layout guard covering the boundary.
- DONE 2026-05-25: startup tests now share the official `startup_monitor_factory` fixture from `tests/conftest.py`, with the startup contract layout guard preventing local monitor factory copies from returning.
- DONE 2026-05-25: startup health-check tests now share the official `startup_health_check_connection` fixture from `tests/conftest.py`, with the startup contract layout guard preventing local connection helper copies from returning.
- DONE 2026-05-26: residual startup structural guards now live in `tests/unit/test_startup_guard_contract_layout.py`, and the empty `tests/unit/test_startup_guards.py` monolith was removed after all functional startup contracts were split out.
- DONE 2026-05-21: monitor execution-contract tests (`execute_trade*` and `_await_order_fill`) are split out of the `test_monitor.py` monolith into `tests/unit/test_monitor_execution.py`, with a layout guard preventing them from sliding back.
- DONE 2026-05-21: monitor closing-contract tests (`test_close_position*`) are split out of the `test_monitor.py` monolith into `tests/unit/test_monitor_closing.py`, with the contract layout guard covering the new boundary.
- DONE 2026-05-22: monitor price-guard tests (`missing_price`, impossible crypto prices, and repeated Alpaca crypto snapshot/quote-mid staleness) are split out of the `test_monitor.py` monolith into `tests/unit/test_monitor_price_guard.py`, with the contract layout guard covering the boundary.
- DONE 2026-05-22: monitor process-pair/ledger-state tests (Kalman invalid/quarantine/rebuild, orchestrator/profit vetoes, and failed execution status) are split out of the `test_monitor.py` monolith into `tests/unit/test_monitor_process_pair.py`, with the contract layout guard covering the boundary.
- DONE 2026-05-26: monitor contract tests now share the official `monitor` fixture from `tests/conftest.py`, with the monitor contract layout guard preventing local monitor fixture copies from returning.
- DONE 2026-05-26: monitor concurrency tests now use the shared `monitor` fixture instead of direct `ArbitrageMonitor` construction, with the monitor contract layout guard covering that file too.
- DONE 2026-05-26: spread-guard monitor tests now use the shared `monitor` fixture instead of direct `ArbitrageMonitor` construction, with the monitor contract layout guard covering that file too.
- DONE 2026-05-26: dashboard runtime preflight tests now use the shared `monitor` fixture instead of direct `ArbitrageMonitor` construction, with the monitor contract layout guard covering that file too.
- DONE 2026-05-20: dashboard wallet sync now fails closed when requested budget exceeds effective Alpaca cash instead of deferring an oversized buy to the broker.
- DONE 2026-05-20: WalletPanel disables broker buys and shows a reduce-budget warning when the recommendation plan is cash-limited, matching the backend fail-closed wallet-buy behavior.
- DONE 2026-05-19: equity pair-spread confidence no longer receives a long-only Sortino penalty that could drag a `0.60` orchestrator score below the `0.5` execution threshold.
- DONE 2026-05-19: low `global_strategy_accuracy` now emits an orchestrator warning instead of silently multiplying pair-spread confidence below the execution threshold; high-accuracy boosting remains unchanged.
- DONE 2026-05-19: cost-scaled entry thresholds now scale gradually from `MONITOR_ENTRY_ZSCORE_COST_BASELINE` to `PAIR_MAX_ROUND_TRIP_COST_PCT`, so moderate accepted costs no longer jump straight to the cap.
- DONE 2026-05-19: neutral/default SEC fundamental scores no longer drag pair-spread MAB confidence below bull/bear agent consensus; low fundamental scores still use the existing veto path.

## P2 - Must fix before public release / monetization

- DONE 2026-05-20: monitor logging now honors `LOG_LEVEL` from settings, covered by a regression test.
- Add durable structured logs.
- Reconcile local runtime docs with Python 3.14 usage, absent npm, and absent Gradle wrapper on this machine.

## P3 - Can wait

- Improve market-regime hot-path latency once paper launch blockers are resolved.
