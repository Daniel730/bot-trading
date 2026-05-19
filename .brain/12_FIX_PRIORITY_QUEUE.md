# Fix Priority Queue

Last updated: 2026-05-19

## P0 - Must fix before broker-connected testing

- Runtime dependencies are currently unavailable locally: Docker, Redis, Postgres, dashboard, and execution-engine preflight checks failed on 2026-05-19.
- DONE 2026-05-19: Telegram notification exception output now redacts bot tokens and Telegram API bot URLs before printing/logging.
- Rotate the leaked Telegram bot token and purge or sanitize historical `logs/recovery_window.log` before any operator-facing launch.
- DONE 2026-05-19: crypto spread-guard bid/ask sourcing now falls back to Alpaca crypto snapshot quotes when yfinance reports zero bid/ask, while still failing closed if no positive quote exists.
- DONE 2026-05-19: completed scan iterations now append durable JSONL trade decision reports under `logs/trade_decision_reports.jsonl`.

## P1 - Must fix before extended personal testing

- DONE 2026-05-19: dashboard runtime config updates now validate the resulting `Settings` guardrails before persisting; unsafe `PAPER_TRADING=false` with `LIVE_CAPITAL_DANGER=false` is rejected.
- Log `process_pair()` skip reasons for market closed, non-cointegrated pairs, and missing latest prices.
- Persist paper trade entry context before shadow execution returns so paper trades retain decision evidence.
- Decide whether the Python monitor should route through the Java execution engine or update architecture docs/tests to match direct brokerage execution.
- Review cost-scaled entry thresholds by venue; current EUR-account US equity threshold can rise from `2.2` to about `6.6`.

## P2 - Must fix before public release / monetization

- Wire `LOG_LEVEL` into monitor logging and add durable structured logs.
- Reconcile local runtime docs with Python 3.14 usage, absent npm, and absent Gradle wrapper on this machine.

## P3 - Can wait

- Improve market-regime hot-path latency once paper launch blockers are resolved.
