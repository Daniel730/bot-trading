Audit only the order execution logic.

Look for bugs involving:

1. Duplicate orders.
2. Missing idempotency/client order IDs.
3. Partial fills.
4. One leg filled and the other failed.
5. One leg filled and the other delayed.
6. Rejected orders.
7. Cancelled orders.
8. Retry logic causing repeated exposure.
9. Using requested quantity instead of filled quantity.
10. Using expected price instead of average fill price.
11. Ignoring fees or slippage.
12. Incorrect order side: buy/sell inverted.
13. Incorrect symbol mapping across exchanges.
14. Incorrect precision/rounding.
15. Incorrect min order size.
16. Balance checked before but changed before execution.
17. Open position not reconciled after restart.

For every bug:

- Show exact code.
- Explain failure scenario.
- Explain financial damage.
- Give minimal safe fix.
- Give test case.

Before proposing a fix, explain the concrete sequence of events that makes this bug happen.
If you cannot reproduce or reason through the bug from the code, mark it as a risk, not a confirmed bug.
