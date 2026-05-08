Audit error handling and retry logic.

Look for:

1. except Exception hiding failures.
2. Errors logged but workflow continues incorrectly.
3. Retry without idempotency.
4. Retry after partial success.
5. Retry after unknown order status.
6. Network timeout treated as order failure.
7. Exchange error parsed incorrectly.
8. Rate-limit error handled like normal failure.
9. Missing circuit breaker.
10. Missing kill switch.
11. Missing rollback/hedge path.
12. Missing reconciliation after crash.
13. Alerts sent but state not changed.
14. Bot continuing after critical invariant is broken.

For every issue:

- Explain what exception or response triggers it.
- Explain what the code currently does.
- Explain what it should do instead.
- Explain whether the bot should continue, pause, hedge, cancel, or shut down.
- Add a test case.

Before proposing a fix, explain the concrete sequence of events that makes this bug happen.
If you cannot reproduce or reason through the bug from the code, mark it as a risk, not a confirmed bug.
