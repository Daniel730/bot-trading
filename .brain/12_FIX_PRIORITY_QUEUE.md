# Fix Priority Queue

Last updated: 2026-05-20

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
- DONE 2026-05-20: crypto latest prices now pass coarse per-symbol sanity checks before Kalman update, blocking impossible cross-assigned prices such as BTC near $9 or ETH near BTC prices before state can be poisoned.
- DONE 2026-05-20: chunked latest-price fetches now serialize crypto chunks, preventing concurrent yfinance crypto fallback calls from cross-assigning ticker prices when Alpaca/Polygon do not fill the batch.
- DONE 2026-05-20: trade decision reports now include latest price values, price source labels, and explicit rejection reasons per pair so skipped/blocked trades are easier to audit.
- DONE 2026-05-20: spread-guard blocks now carry bid/ask values, leg spread percentages, total spread percentage, and configured max spread into execution diagnostics and trade decision reports.
- DONE 2026-05-20: unprofitable profit-guard vetoes now carry gross profit, friction, net profit, sizing, z-score, and spread inputs into execution diagnostics and trade decision reports.
- DONE 2026-05-20: profit-preview math now fails closed when a candidate entry is already at or beyond the configured statistical stop-loss z-score instead of showing positive expected profit with zero loss risk.
- DONE 2026-05-20: repeated unchanged Alpaca crypto snapshot price tuples now fail closed before Kalman updates so stale live-data snapshots cannot create or preserve bad signal state.
- DONE 2026-05-20: latest crypto prices now use newer Alpaca quote midpoints, with quote source and timestamp metadata, when the snapshot trade price is older than the quote.
- DONE 2026-05-20: repeated unchanged Alpaca crypto quote-mid timestamps now fail closed before Kalman updates, preventing frozen quote midpoint data from silently driving signal math.
- DONE 2026-05-20: crypto snapshot stale-repeat cadence is now intentionally pinned at 5 scans and covered by a regression test, resolving the dirty runtime/test mismatch.
- DONE 2026-05-20: compose files are pinned to LF line endings and normalized, resolving noisy dirty compose diffs without runtime behavior changes.
- DONE 2026-05-20: trade decision reports now include per-leg latest price timestamps, making quote-mid freshness visible in every scan report.
- DONE 2026-05-20: local Docker runtime was rebuilt from current code, `.env` was repaired from stale `POSTGRES_PASSWORD=bot_pass`/`DATABASE_URL` defaults to the existing Postgres volume secret, and live decision reports confirmed `alpaca_crypto_quote_mid` price sources plus per-leg price timestamps.
- DONE 2026-05-19: completed scan iterations now append durable JSONL trade decision reports under `logs/trade_decision_reports.jsonl`.

## P1 - Must fix before extended personal testing

- DONE 2026-05-19: dashboard runtime config updates now validate the resulting `Settings` guardrails before persisting; unsafe `PAPER_TRADING=false` with `LIVE_CAPITAL_DANGER=false` is rejected.
- DONE 2026-05-19: `process_pair()` diagnostics and trade decision reports now include skip reasons such as `market_closed`, `not_cointegrated`, `missing_price`, `kalman_unavailable`, and `below_entry_threshold`.
- DONE 2026-05-19: paper shadow entries now write `TradeJournal` context before shadow ledger execution, including z-score, entry threshold, confidence, verdict, regime, and sizing metrics.
- DONE 2026-05-19: architecture docs/tests now state that `src/monitor.py` paper orders use `shadow_service`, broker-connected orders use Python `BrokerageService`, and the Java execution engine is a dry-run/audit sidecar rather than the monitor's default order path.
- DONE 2026-05-19: dashboard wallet buy endpoints now fail closed with HTTP 409 while `PAPER_TRADING=true` instead of returning fake successful paper order IDs that never reach Alpaca.
- DONE 2026-05-20: dashboard wallet sync now fails closed when requested budget exceeds effective Alpaca cash instead of deferring an oversized buy to the broker.
- DONE 2026-05-20: WalletPanel disables broker buys and shows a reduce-budget warning when the recommendation plan is cash-limited, matching the backend fail-closed wallet-buy behavior.
- DONE 2026-05-19: equity pair-spread confidence no longer receives a long-only Sortino penalty that could drag a `0.60` orchestrator score below the `0.5` execution threshold.
- DONE 2026-05-19: low `global_strategy_accuracy` now emits an orchestrator warning instead of silently multiplying pair-spread confidence below the execution threshold; high-accuracy boosting remains unchanged.
- DONE 2026-05-19: cost-scaled entry thresholds now scale gradually from `MONITOR_ENTRY_ZSCORE_COST_BASELINE` to `PAIR_MAX_ROUND_TRIP_COST_PCT`, so moderate accepted costs no longer jump straight to the cap.
- DONE 2026-05-19: neutral/default SEC fundamental scores no longer drag pair-spread MAB confidence below bull/bear agent consensus; low fundamental scores still use the existing veto path.

## P2 - Must fix before public release / monetization

- Wire `LOG_LEVEL` into monitor logging and add durable structured logs.
- Reconcile local runtime docs with Python 3.14 usage, absent npm, and absent Gradle wrapper on this machine.

## P3 - Can wait

- Improve market-regime hot-path latency once paper launch blockers are resolved.
