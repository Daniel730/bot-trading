# Current Backlog And Open Risks

Last refreshed: 2026-04-30.

This is the current human-readable backlog. Older audit files are preserved for context, but this file is the preferred short list.

## Highest Priority

1. Live Java brokerage is intentionally blocked.
   `execution-engine/Application.java` refuses `DRY_RUN=false`. Keep it that way until a real, tested `LiveBroker` is wired with integration tests.

2. Trading 212 timeout recovery cannot fully correlate broker orders.
   `BrokerageService` keeps a local `client_order_id`, but Trading 212's public order schema does not accept that field. Timeout recovery should be redesigned around broker-returned order ids or post-submit reconciliation that can reliably match ticker, signed quantity, timestamp, and price band.

3. Partial fills are still not modeled end-to-end.
   The Python live path logs requested quantities after broker success. Add order-status polling or broker execution reports, then persist filled quantity, average fill price, and remaining quantity per leg.

4. Live Web3 path needs production-grade wallet safeguards.
   Keep Web3 execution behind explicit operator configuration. Add allowance checks, quote/slippage previews, chain-id confirmation, nonce handling, and testnet/mainnet separation before meaningful capital.

## Reliability

5. Requirements are still loose.
   `requirements.txt` is human-readable but not fully pinned. Add a generated lock file or constraints file for reproducible Docker builds.

6. Some diagnostic output bypasses structured logging.
   There are still `print()`/`System.err` style diagnostics in a few paths. Convert them to module loggers so dashboard log ingestion stays consistent.

7. FastMCP and dashboard API are separate surfaces.
   `src/mcp_server.py` exposes tool calls on port `8000`; `dashboard_service` serves the operator API on `8080`. Review auth and exposure expectations before binding either port publicly.

8. Pair universe is large and eligibility-driven.
   Keep a close eye on startup time, provider rate limits, and rejection summaries after edits to `settings.ARBITRAGE_PAIRS`.

## Strategy And Data Quality

9. Corporate actions are not a complete first-class invalidation path.
   Historical data uses adjusted series in many paths, but pair state should still be explicitly invalidated around splits, symbol changes, and special dividends.

10. Market calendar handling is approximate by venue suffix.
    `monitor.get_market_config()` uses suffix-based windows. Add exchange calendars and holidays for robust multi-region operation.

11. SEC/fundamental cache misses default to neutral.
    This keeps the hot path alive, but it can let structurally unknown names pass through unless other agents veto. Consider stricter policy for live mode.

12. Whale watcher depends on external cache freshness.
    Provider ingestion should refresh Redis summaries outside the orchestrator hot path. Add stale-cache telemetry.

## Testing Gaps

13. Add live-path contract tests with fake T212/Alpaca/Web3 providers.
    Focus on signed quantity, limit price rounding, min quantity, timeout/retry behavior, budget update, and emergency close.

14. Add dashboard auth regression tests.
    Cover token + session headers, SSE auth, WebSocket first-message auth, CORS, 2FA setup, and sensitive config writes.

15. Add Java gRPC health/status tests.
    Cover empty legs, null L2 book, stale L2 book, duplicate client order id, kill switch, and repository/Redis error behavior.

16. Add pair-eligibility regression fixtures.
    Include US, XETRA, Euronext, LSE, HK, cross-currency, crypto, and mixed crypto/equity examples.
