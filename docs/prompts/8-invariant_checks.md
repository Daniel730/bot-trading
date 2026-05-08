Audit data integrity across the whole bot.

Check for:

1. Incorrect symbol format between exchanges.
2. Wrong base/quote interpretation.
3. Price precision issues.
4. Quantity precision issues.
5. Decimal vs float bugs.
6. Currency conversion bugs.
7. Timezone bugs.
8. Timestamp units: seconds vs milliseconds.
9. Naive datetime vs aware datetime.
10. Negative/zero prices or quantities.
11. Missing validation on API responses.
12. Cached data used after expiry.
13. Database state disagreeing with exchange state.
14. Portfolio state not reconciled.
15. PnL calculated from intended trade instead of actual fill.

For each bug:

- Show source of corrupted data.
- Show where it spreads.
- Explain final consequence.
- Give validation/invariant checks.

Before proposing a fix, explain the concrete sequence of events that makes this bug happen.
If you cannot reproduce or reason through the bug from the code, mark it as a risk, not a confirmed bug.
